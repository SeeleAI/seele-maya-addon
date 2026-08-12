"""Maya plug-in entry point and receiver lifecycle."""
try:
    import maya.api.OpenMaya as om
except ImportError:
    om = None

class SeeleMayaStatus(om.MPxCommand if om else object):
    def doIt(self,args):
        from seele_maya.bridge.server import status
        self.setResult(str(status()))

def _creator(): return SeeleMayaStatus()

def initializePlugin(plugin):
    if om:
        fn = om.MFnPlugin(plugin, "SEELE", "0.1.0", "Any")
        fn.registerCommand("seeleMayaStatus",_creator)
    from seele_maya.bridge.server import start
    start()

def uninitializePlugin(plugin):
    from seele_maya.bridge.server import stop
    stop()
    if om:
        om.MFnPlugin(plugin).deregisterCommand("seeleMayaStatus")
