import os, sys, unittest
sys.path.insert(0,os.path.abspath('SeeleMaya/scripts'))
from seele_maya.maya_api.importer import MayaImporter

class FakeCmds(object):
    def __init__(self,translators=(),commands=()): self.loaded=set(); self.translators=set(translators); self.commands=set(commands)
    def pluginInfo(self,name,query=False,loaded=False): return name in self.loaded
    def loadPlugin(self,name,quiet=False): self.loaded.add(name)
    def translator(self,query=False,list=False): return tuple(self.translators)
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
