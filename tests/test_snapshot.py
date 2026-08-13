import os,sys,unittest
from unittest.mock import patch
sys.path.insert(0,os.path.abspath('SeeleMaya/scripts'))
from seele_maya.maya_api import snapshot
from seele_maya.maya_api.importer import MayaImporter

class FakeScene(object):
    def __init__(self): self.nodes={'old':'|old','new':'|new'}; self.deleted=[]; self.ns=':'; self.selection=[]; self.namespaces={':','seele_x'}
    def ls(self,value=None,long=False,uuid=False,selection=False):
        if selection:return list(self.selection)
        if uuid:return [next((key for key,node in self.nodes.items() if node==value),value if value in self.nodes else '')]
        if value is not None:return [self.nodes[value]] if value in self.nodes else []
        return list(self.nodes.values())
    def namespaceInfo(self,currentNamespace=False,listOnlyNamespaces=False,recurse=False): return self.ns if currentNamespace else list(self.namespaces)
    def namespace(self,setNamespace=None,exists=None,removeNamespace=None,mergeNamespaceWithRoot=False):
        if setNamespace is not None:self.ns=setNamespace
        if exists is not None:return exists in self.namespaces
        if removeNamespace is not None:self.namespaces.discard(removeNamespace)
    def currentTime(self,value=None,query=False,edit=False): return 1
    def playbackOptions(self,query=False,**kwargs): return 1
    def currentUnit(self,query=False,linear=False,time=False,**kwargs): return 'cm' if linear else 'film'
    def upAxis(self,query=False,axis=False,**kwargs): return 'y'
    def objExists(self,node): return node in self.nodes.values()
    def select(self,*args,**kwargs): pass
    def delete(self,nodes):
        for node in nodes:
            self.deleted.append(node)
            for key,value in list(self.nodes.items()):
                if value==node:self.nodes.pop(key)

class TestSnapshot(unittest.TestCase):
    def test_uuid_delta_and_rollback(self):
        cmds=FakeScene(); cmds.nodes={'old':'|old'}; before=snapshot.capture(cmds); cmds.nodes['new']='|new'; delta=snapshot.diff(cmds,before); self.assertEqual(('new',),delta['createdUuids'])
        self.assertEqual('new',delta['createdNodeMetadata'][0]['uuid']); self.assertEqual('|new',delta['createdNodeMetadata'][0]['node'])
        result={'snapshot':before,'createdUuids':delta['createdUuids'],'namespace':'seele_x'}; self.assertTrue(snapshot.rollback(cmds,result)); self.assertNotIn('new',cmds.nodes)
    def test_incomplete_rollback_is_reported(self):
        class UndeletableScene(FakeScene):
            def delete(self,nodes): pass
        cmds=UndeletableScene(); cmds.nodes={'old':'|old'}; before=snapshot.capture(cmds); cmds.nodes['new']='|new'
        with self.assertRaisesRegex(snapshot.RollbackError,'ROLLBACK_INCOMPLETE'): snapshot.rollback(cmds,{'snapshot':before,'createdUuids':('new',),'namespace':'seele_x'})
    def test_restore_failure_rolls_back_scene_delta(self):
        cmds=FakeScene(); importer=MayaImporter(cmds); before=snapshot.capture(cmds); cmds.nodes['later']='|later'; calls=[]
        with patch('seele_maya.maya_api.importer.snapshot.restore_environment',side_effect=RuntimeError('restore failed')), patch.object(importer,'rollback',side_effect=lambda result: calls.append(result)):
            with self.assertRaisesRegex(RuntimeError,'restore failed'): importer._restore_or_rollback(before,'seele_x')
        self.assertEqual(('later',),calls[0]['createdUuids'])
    def test_restore_and_rollback_failure_reports_rollback_error(self):
        cmds=FakeScene(); importer=MayaImporter(cmds); before=snapshot.capture(cmds)
        with patch('seele_maya.maya_api.importer.snapshot.restore_environment',side_effect=RuntimeError('restore failed')), patch.object(importer,'rollback',side_effect=RuntimeError('delete failed')):
            with self.assertRaisesRegex(snapshot.RollbackError,'ROLLBACK_FAILED'): importer._restore_or_rollback(before,'seele_x')
