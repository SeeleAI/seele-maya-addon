"""Minimal real-Maya load/probe/unload smoke test. Run with mayapy."""
from __future__ import print_function

import os
import sys

ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS=os.path.join(ROOT,"SeeleMaya","scripts")
PLUGIN=os.path.join(ROOT,"SeeleMaya","plug-ins","seele_maya_plugin.py")
if SCRIPTS not in sys.path: sys.path.insert(0,SCRIPTS)

import maya.standalone
import maya.cmds as cmds

maya.standalone.initialize(name="python")
try:
    cmds.loadPlugin(PLUGIN,quiet=True)
    from seele_maya.maya_api.importer import get_importer
    results={name:get_importer().readiness(name,refresh=True) for name in ("fbx","obj","abc","dae","usd","usda","usdc")}
    assert not results["usd"]["ready"] and not results["usda"]["ready"] and not results["usdc"]["ready"]
    print(results)
    cmds.unloadPlugin(PLUGIN,force=True)
finally:
    maya.standalone.uninitialize()
