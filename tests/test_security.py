import os, socket, sys, tempfile, unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone
sys.path.insert(0,os.path.abspath('SeeleMaya/scripts'))
from seele_maya.contract.validator import _validate_path, ContractError
from seele_maya.transfer.downloader import ByteBudget
from seele_maya.transfer.staging import safe_path, _assert_no_links, staged_file
import seele_maya.transfer.downloader as downloader

class TestPaths(unittest.TestCase):
    def test_windows_paths(self):
        for value in ('C:/x.fbx','C:x.fbx','//server/share/x.fbx','x:stream','CON','x.','x '):
            with self.assertRaises(ContractError,msg=value): _validate_path(value)
    def test_safe_path(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertTrue(safe_path(root,'assets/a.fbx').startswith(root))
            with self.assertRaises(ValueError): safe_path(root,'../a.fbx')
    def test_symlink_parent_rejected(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as outside:
            link=os.path.join(root,'files','linked'); os.makedirs(os.path.dirname(link))
            try: os.symlink(outside,link,target_is_directory=True)
            except (OSError,NotImplementedError): self.skipTest('symlink creation is unavailable')
            with self.assertRaises(ValueError): safe_path(root,'linked/a.fbx')
    def test_trusted_boundary_does_not_inspect_system_ancestors(self):
        with tempfile.TemporaryDirectory() as root:
            child=os.path.join(root,'staging'); os.mkdir(child)
            # A platform alias such as macOS /var -> /private/var is outside the
            # trusted data root and must not make a safe staging child fail.
            _assert_no_links(child,root)
    @unittest.skipUnless(os.name=='nt','Windows handle-relative staging only')
    def test_windows_handle_relative_write_and_rename(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root,'files','nested'))
            with staged_file(root,'nested/a.bin') as output:
                output.write(b'abc'); output.commit()
            with open(os.path.join(root,'files','nested','a.bin'),'rb') as stream:self.assertEqual(b'abc',stream.read())

class TestBudget(unittest.TestCase):
    def test_transfer_total(self):
        budget=ByteBudget(10); budget.add(6)
        with self.assertRaises(ValueError): budget.add(5)

class TestDownloadNetwork(unittest.TestCase):
    def test_idna_is_canonicalized_and_allowlist_is_exact(self):
        old=downloader.ALLOWED_DOWNLOAD_HOSTS; downloader.ALLOWED_DOWNLOAD_HOSTS=('xn--bcher-kva.example',)
        try:
            self.assertTrue(downloader.url_allowed('https://bücher.example/model.fbx'))
            self.assertFalse(downloader.url_allowed('https://cdn.xn--bcher-kva.example/model.fbx'))
        finally: downloader.ALLOWED_DOWNLOAD_HOSTS=old
    def test_private_dns_answer_is_rejected(self):
        record=(socket.AF_INET,socket.SOCK_STREAM,6,'',('127.0.0.1',443))
        with patch('seele_maya.transfer.downloader.socket.getaddrinfo',return_value=[record]):
            with self.assertRaisesRegex(ValueError,'DNS_ADDRESS_UNSAFE'): downloader._public_addresses('assets.example')
    def test_content_length_is_checked_before_body(self):
        class Response(object):
            def __init__(self,value): self.value=value
            def getheader(self,name): return self.value
        budget=downloader.ByteBudget(100)
        downloader._preflight_length(Response('10'),10,budget)
        with self.assertRaisesRegex(ValueError,'SIZE_MISMATCH'): downloader._preflight_length(Response('11'),10,budget)
        with self.assertRaisesRegex(ValueError,'SIZE_MISMATCH'): downloader._preflight_length(Response('-1'),10,budget)
        with self.assertRaisesRegex(ValueError,'SIZE_LIMIT_EXCEEDED'): downloader._preflight_length(Response('60'),60,downloader.ByteBudget(50))
