import threading

def execute(callable_):
    """Run Maya work on its main thread and propagate the result."""
    try:
        import maya.utils
    except ImportError:
        return callable_()
    if threading.current_thread() is threading.main_thread():
        return callable_()
    return maya.utils.executeInMainThreadWithResult(callable_)
