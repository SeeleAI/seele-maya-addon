# Maya runtime tests

These tests must be run with each supported Maya `mayapy`, not regular CPython:

```powershell
& "C:\Program Files\Autodesk\Maya2022\bin\mayapy.exe" tests_maya\smoke.py
```

The smoke test initializes Maya standalone, loads the receiver plug-in, probes runtime formats, then unloads it. A passing result is runtime evidence only for that exact Maya/OS build. Golden FBX/OBJ/ABC import and cancellation fixtures are still required before release.
