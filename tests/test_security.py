import os, sys, tempfile, unittest
from datetime import datetime, timedelta, timezone
sys.path.insert(0,os.path.abspath('SeeleMaya/scripts'))
from seele_maya.contract.validator import _validate_path, ContractError
from seele_maya.transfer.downloader import ByteBudget
from seele_maya.transfer.staging import safe_path

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

class TestBudget(unittest.TestCase):
    def test_transfer_total(self):
        budget=ByteBudget(10); budget.add(6)
        with self.assertRaises(ValueError): budget.add(5)
