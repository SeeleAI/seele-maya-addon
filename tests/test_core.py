import os, sys, tempfile, threading, unittest, uuid
from unittest.mock import patch
sys.path.insert(0, os.path.abspath('SeeleMaya/scripts'))
from seele_maya.bridge.challenge import ChallengeStore
from seele_maya.transfer.manager import TransferManager
from seele_maya.transfer.manager import _safe_error
from seele_maya.contract.validator import ContractError
import seele_maya.transfer.downloader as downloader
from seele_maya.config import DEFAULT_ALLOWED_DOWNLOAD_HOSTS

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
    def test_official_hosts_are_allowed_by_default(self):
        expected=(
            'static.seeles.ai',
            'seele-asset-public-1.s3.ap-southeast-1.amazonaws.com',
            'd3lzqljvieno0e.cloudfront.net',
            'seelemedia.s3.us-east-1.amazonaws.com',
            'seelemedia.s3.amazonaws.com',
            'seeleh5.blob.core.windows.net',
            'd3vhd1f81y5p6c.cloudfront.net',
        )
        self.assertEqual(expected,DEFAULT_ALLOWED_DOWNLOAD_HOSTS)
        for host in expected: self.assertTrue(downloader._allowed('https://'+host+'/asset.fbx'),host)
        self.assertFalse(downloader._allowed('https://static.seeles.ai.evil.example/asset.fbx'))
        self.assertFalse(downloader._allowed('https://evilstatic.seeles.ai/asset.fbx'))
    def test_exact_and_subdomain(self):
        old=downloader.ALLOWED_DOWNLOAD_HOSTS; downloader.ALLOWED_DOWNLOAD_HOSTS=('assets.example.com',)
        try:
            self.assertTrue(downloader._allowed('https://assets.example.com/a.fbx'))
            self.assertTrue(downloader._allowed('https://cdn.assets.example.com/a.fbx'))
            self.assertFalse(downloader._allowed('https://assets.example.com.evil/a.fbx'))
            self.assertFalse(downloader._allowed('http://assets.example.com/a.fbx'))
            self.assertFalse(downloader._allowed('https://assets.example.com:444/a.fbx'))
            downloader.ALLOWED_DOWNLOAD_HOSTS=('127.0.0.1',)
            self.assertFalse(downloader._allowed('https://127.0.0.1/a.fbx'))
        finally: downloader.ALLOWED_DOWNLOAD_HOSTS=old

class TestManager(unittest.TestCase):
    def test_typed_dependency_error_is_preserved(self):
        error=_safe_error(ContractError('DEPENDENCY_MISSING','local detail'),'IMPORT_FAILED','import')
        self.assertEqual('DEPENDENCY_MISSING',error['code']); self.assertNotIn('local detail',error['message'])
    def test_arbitrary_exception_is_not_public_code(self):
        self.assertEqual('IMPORT_FAILED',_safe_error(RuntimeError('SOME_RANDOM_CODE'),'IMPORT_FAILED','import')['code'])
    def test_readiness_error_keeps_code_and_stage(self):
        error=_safe_error(ContractError('FBX_PLUGIN_UNAVAILABLE','local detail','readiness'),'DOWNLOAD_FAILED','download')
        self.assertEqual('FBX_PLUGIN_UNAVAILABLE',error['code']); self.assertEqual('readiness',error['stage'])
    def test_primary_import_error_keeps_nested_rollback_detail(self):
        from seele_maya.transfer.manager import _with_rollback_detail
        primary=RuntimeError('IMPORT_CREATED_NO_NODES'); primary.rollback_error=RuntimeError('ROLLBACK_FAILED')
        error=_with_rollback_detail(_safe_error(primary,'IMPORT_FAILED','import'),primary)
        self.assertEqual('IMPORT_CREATED_NO_NODES',error['code']); self.assertEqual('import',error['stage'])
        self.assertEqual('ROLLBACK_FAILED',error['rollback']['code']); self.assertEqual('rollback',error['rollback']['stage'])
    def test_warning_deduplication(self):
        from seele_maya.transfer.manager import _append_warnings
        item={'warnings':[]}; warning={'code':'OBJ_MTL_NOT_PROVIDED','path':'missing.mtl'}
        _append_warnings(item,[warning,dict(warning)])
        self.assertEqual([warning],item['warnings'])
    def test_cancel_rollback_failure_is_terminal_failed(self):
        class Importer(object):
            def rollback(self,result): raise RuntimeError('ROLLBACK_FAILED')
        manager=TransferManager(); manager.importer=Importer(); tid=str(uuid.uuid4()); event=threading.Event(); event.set(); manager.items[tid]={"transferId":tid,"state":"cancel_pending","cancel":event,"warnings":[],"createdAt":"x","updatedAt":"x","manifest":{},"digest":"x"}
        self.assertFalse(manager._rollback_cancelled_import(tid,{})); self.assertEqual('failed',manager.get(tid)['state']); self.assertEqual('ROLLBACK_FAILED',manager.get(tid)['error']['code'])
    def test_success_cleans_staging(self):
        class Importer(object):
            def readiness(self,name,refresh=False): return {'ready':True,'reason':None}
            def import_transfer(self,item,root): return {'group':'g','namespace':'n','nodesCreated':1,'createdUuids':(),'snapshot':{},'warnings':[]}
            def rollback(self,result): return True
        manager=TransferManager(); manager.importer=Importer(); tid=str(uuid.uuid4()); item={'transferId':tid,'state':'accepted','cancel':threading.Event(),'warnings':[],'createdAt':'x','updatedAt':'x','manifest':{'target':{'format':'fbx'},'entryFileId':'m','files':[{'id':'m'}]},'digest':'x'}; manager.items[tid]=item; cleaned=[]
        with tempfile.TemporaryDirectory() as root, patch('seele_maya.transfer.manager.staging_root',return_value=root), patch('seele_maya.transfer.manager.download_file'), patch('seele_maya.transfer.manager.validate_dependencies'), patch('seele_maya.transfer.manager.cleanup_staging',side_effect=lambda value: cleaned.append(value)):
            manager._run(tid)
        self.assertEqual('completed',manager.get(tid)['state']); self.assertEqual([root],cleaned)
    def test_dependency_warning_completes_with_warnings(self):
        class Importer(object):
            def readiness(self,name,refresh=False): return {'ready':True,'reason':None}
            def import_transfer(self,item,root): return {'group':'g','namespace':'n','nodesCreated':1,'warnings':[]}
            def rollback(self,result): return True
        manager=TransferManager(); manager.importer=Importer(); tid=str(uuid.uuid4())
        item={'transferId':tid,'state':'accepted','cancel':threading.Event(),'warnings':[],'createdAt':'x','updatedAt':'x','manifest':{'target':{'format':'obj'},'entryFileId':'m','files':[{'id':'m'}]},'digest':'x'}; manager.items[tid]=item
        warning={'code':'OBJ_MTL_NOT_PROVIDED','message':'OBJ material library was not provided','path':'missing.mtl'}
        with tempfile.TemporaryDirectory() as root, patch('seele_maya.transfer.manager.staging_root',return_value=root), patch('seele_maya.transfer.manager.download_file'), patch('seele_maya.transfer.manager.validate_dependencies',return_value={'warnings':[warning]}), patch('seele_maya.transfer.manager.cleanup_staging'):
            manager._run(tid)
        result=manager.get(tid); self.assertEqual('completed_with_warnings',result['state']); self.assertEqual([warning],result['warnings'])
    def test_cancel_before_import_cleans_staging(self):
        manager=TransferManager(); tid=str(uuid.uuid4()); event=threading.Event(); event.set(); item={'transferId':tid,'state':'accepted','cancel':event,'warnings':[],'createdAt':'x','updatedAt':'x','manifest':{'target':{'format':'fbx'},'entryFileId':'m','files':[{'id':'m'}]},'digest':'x'}; manager.items[tid]=item; cleaned=[]
        with tempfile.TemporaryDirectory() as root, patch('seele_maya.transfer.manager.staging_root',return_value=root), patch('seele_maya.transfer.manager.download_file'), patch('seele_maya.transfer.manager.validate_dependencies'), patch('seele_maya.transfer.manager.cleanup_staging',side_effect=lambda value: cleaned.append(value)):
            manager._run(tid)
        self.assertEqual('cancelled',manager.get(tid)['state']); self.assertEqual([root],cleaned)
    def test_conflict(self):
        manager=TransferManager(); manager._run=lambda tid: None
        tid=str(uuid.uuid4()); base={'transferId':tid,'displayName':'a','files':[]}
        manager.accept(base); manager.accept(dict(base))
        changed=dict(base); changed['displayName']='b'
        with self.assertRaises(ValueError): manager.accept(changed)
    def test_transition_guard(self):
        manager=TransferManager(); manager._run=lambda tid: None
        item=manager.accept({'transferId':str(uuid.uuid4()),'files':[]})
        with self.assertRaises(ValueError): manager.transition(item['transferId'],'completed')
    def test_shutdown_rejects_new_transfer(self):
        manager=TransferManager(); manager.shutdown(0)
        with self.assertRaisesRegex(ValueError,'RECEIVER_STOPPING'): manager.accept({'transferId':str(uuid.uuid4()),'files':[]})
    def _cancel_import_state(self,state):
        class Importer(object):
            def __init__(self): self.rollback_calls=0
            def rollback(self,result): self.rollback_calls+=1
        manager=TransferManager(); manager.importer=Importer(); tid=str(uuid.uuid4()); event=threading.Event()
        manager.items[tid]={"transferId":tid,"state":state,"cancel":event,"warnings":[],"createdAt":"x","updatedAt":"x","manifest":{},"digest":"x"}
        event.set()
        if state=="importing_geometry": manager.transition(tid,"cancel_pending")
        else: manager.transition(tid,"cancel_pending")
        manager._finish_import(tid,{"group":"g","namespace":"n","nodesCreated":1,"createdNodes":["g"]})
        self.assertEqual("cancelled",manager.get(tid)["state"]); self.assertEqual(1,manager.importer.rollback_calls)
    def test_cancel_importing_rolls_back(self): self._cancel_import_state("importing_geometry")
    def test_cancel_organizing_rolls_back(self): self._cancel_import_state("organizing_scene")
    def test_internal_rollback_is_not_public(self):
        manager=TransferManager(); tid=str(uuid.uuid4()); manager.items[tid]={"transferId":tid,"state":"rollback","cancel":threading.Event(),"warnings":[],"createdAt":"x","updatedAt":"x","manifest":{},"digest":"x"}
        self.assertEqual("cancel_pending",manager.get(tid)["state"])
