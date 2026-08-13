import os, sys, unittest
from unittest.mock import patch
sys.path.insert(0,os.path.abspath('SeeleMaya/scripts'))
from seele_maya.maya_api.importer import MayaImporter

class FakeCmds(object):
    def __init__(self,translators=(),commands=()): self.loaded=set(); self.translators=set(translators); self.commands=set(commands)
    def pluginInfo(self,name,query=False,loaded=False): return name in self.loaded
    def loadPlugin(self,name,quiet=False): self.loaded.add(name)
    def translator(self,name=None,query=False,list=False,loaded=False):
        if list: return tuple(self.translators)
        return name in self.translators
    def file(self,*args,**kwargs): return []
    def commandInfo(self,name,exists=False): return name in self.commands
    def __getattr__(self,name):
        if name in self.commands: return lambda *args,**kwargs: None
        raise AttributeError(name)

class TestReadiness(unittest.TestCase):
    def test_p0_ready(self):
        cmds=FakeCmds(('FBX','OBJ'),('AbcImport',)); importer=MayaImporter(cmds)
        self.assertTrue(importer.readiness('fbx')['ready']); self.assertTrue(importer.readiness('obj')['ready']); self.assertTrue(importer.readiness('abc')['ready'])
    def test_missing_translator_is_not_ready(self):
        result=MayaImporter(FakeCmds()).readiness('obj'); self.assertFalse(result['ready']); self.assertEqual('OBJ_TRANSLATOR_UNAVAILABLE',result['reason'])
    def test_usd_fails_closed_until_import_surface_verified(self):
        result=MayaImporter(FakeCmds()).readiness('usd'); self.assertFalse(result['ready']); self.assertEqual('USD_IMPORT_SURFACE_UNAVAILABLE',result['reason'])
    def test_dae_fails_closed_without_golden_evidence(self):
        result=MayaImporter(FakeCmds(('DAE_FBX',))).readiness('dae'); self.assertFalse(result['ready']); self.assertEqual('DAE_IMPORT_SURFACE_UNAVAILABLE',result['reason'])
    def test_cache_and_refresh(self):
        cmds=FakeCmds(('OBJ',)); importer=MayaImporter(cmds); self.assertTrue(importer.readiness('obj')['ready']); cmds.translators.clear(); self.assertTrue(importer.readiness('obj')['ready']); self.assertFalse(importer.readiness('obj',refresh=True)['ready'])
    def test_abc_import_runs_inside_transfer_namespace(self):
        class AbcCmds(FakeCmds):
            def __init__(self): FakeCmds.__init__(self,commands=('AbcImport',)); self.namespace_calls=[]; self.abc_namespace=None
            def namespace(self,setNamespace=None,**kwargs):
                if setNamespace is not None:self.namespace_calls.append(setNamespace)
            def AbcImport(self,path,mode=None): self.abc_namespace=self.namespace_calls[-1]
        cmds=AbcCmds(); importer=MayaImporter(cmds)
        with patch('seele_maya.maya_api.importer.snapshot.diff',return_value={'createdNodes':('|seele_x:model',)}): nodes=importer._invoke_import('asset.abc','abc','seele_x',{})
        self.assertEqual('seele_x',cmds.abc_namespace); self.assertEqual(['|seele_x:model'],nodes)
