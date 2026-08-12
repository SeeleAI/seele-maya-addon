"""Maya plug-in entry point.  The receiver is intentionally started lazily."""
try:
    import maya.api.OpenMaya as om
except ImportError:
    om = None

_server = None

def initializePlugin(plugin):
    global _server
    if om:
        fn = om.MFnPlugin(plugin, "SEELE", "0.1.0", "Any")
        # The first MVP keeps menu/UI registration optional; receiver startup is
        # exposed as a separate action so initializePlugin never performs I/O.
        try:
            fn.registerCommand("seeleMayaStatus", lambda: None)
        except Exception:
            pass

def uninitializePlugin(plugin):
    if om:
        try:
            om.MFnPlugin(plugin).deregisterCommand("seeleMayaStatus")
        except Exception:
            pass
