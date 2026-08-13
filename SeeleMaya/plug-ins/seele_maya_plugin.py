"""Maya plug-in entry point and receiver lifecycle."""
try:
    import maya.api.OpenMaya as om
    from seele_maya import __version__
except ImportError:
    om = None
    __version__ = "0.2.0"

def maya_useNewAPI():
    """Tell Maya to pass API 2.0 objects to the plug-in entry points."""
    pass

class SeeleMayaStatus(om.MPxCommand if om else object):
    def doIt(self,args):
        from seele_maya.bridge.server import status
        self.setResult(str(status()))

def _creator(): return SeeleMayaStatus()

def initializePlugin(plugin):
    if om:
        fn = om.MFnPlugin(plugin, "SEELE", __version__, "Any")
        fn.registerCommand("seeleMayaStatus",_creator)
    from seele_maya.bridge.server import start
    start()

def uninitializePlugin(plugin):
    from seele_maya.bridge.server import stop
    result=stop()
    if result.get("error")=="WORKERS_STILL_RUNNING":
        raise RuntimeError("Cannot unload SEELE Maya plug-in while transfer workers are still running")
    if om:
        om.MFnPlugin(plugin).deregisterCommand("seeleMayaStatus")
