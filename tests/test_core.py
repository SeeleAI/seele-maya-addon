import os, sys, time, unittest, uuid
sys.path.insert(0, os.path.abspath('SeeleMaya/scripts'))
from seele_maya.bridge.challenge import ChallengeStore
from seele_maya.transfer.manager import TransferManager
import seele_maya.transfer.downloader as downloader

class TestChallenge(unittest.TestCase):
    def test_consume_once(self):
        store=ChallengeStore(60); token,_=store.issue('r','https://app.test')
        self.assertIsNone(store.consume(token,'r','https://app.test'))
        self.assertEqual('CHALLENGE_REPLAYED',store.consume(token,'r','https://app.test'))
    def test_binding(self):
        store=ChallengeStore(60); token,_=store.issue('r','https://app.test')
        self.assertEqual('CHALLENGE_INVALID',store.consume(token,'r','https://evil.test'))
    def test_expired(self):
        store=ChallengeStore(-1); token,_=store.issue('r','o')
        self.assertEqual('CHALLENGE_EXPIRED',store.consume(token,'r','o'))

class TestDownloadUrl(unittest.TestCase):
    def test_exact_and_subdomain(self):
        old=downloader.ALLOWED_DOWNLOAD_HOSTS; downloader.ALLOWED_DOWNLOAD_HOSTS=('assets.example.com',)
        try:
            self.assertTrue(downloader._allowed('https://assets.example.com/a.fbx'))
            self.assertTrue(downloader._allowed('https://cdn.assets.example.com/a.fbx'))
            self.assertFalse(downloader._allowed('https://assets.example.com.evil/a.fbx'))
            self.assertFalse(downloader._allowed('http://assets.example.com/a.fbx'))
        finally: downloader.ALLOWED_DOWNLOAD_HOSTS=old

class TestManager(unittest.TestCase):
    def test_conflict(self):
        manager=TransferManager(); manager._run=lambda tid: None
        tid=str(uuid.uuid4()); base={'transferId':tid,'displayName':'a','files':[]}
        manager.accept(base); manager.accept(dict(base))
        changed=dict(base); changed['displayName']='b'
        with self.assertRaises(ValueError): manager.accept(changed)
