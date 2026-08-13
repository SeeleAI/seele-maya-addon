import os
import platform
from ..formats import FORMAT_SPECS, format_spec
from .. import __version__
from .readiness import ReadinessProbe
from . import snapshot

class MockImporter(object):
    def readiness(self,format_name=None,refresh=False):
        if format_name: return {"ready":False,"provider":format_spec(format_name)["provider"],"reason":"MAYA_UNAVAILABLE"}
        return {name:self.readiness(name) for name in FORMAT_SPECS}
    def import_transfer(self, item, root):
        name=item["manifest"].get("displayName") or "asset"
        safe="".join(c if c.isalnum() or c in "_-" else "_" for c in name).strip("_") or "asset"
        return {"group":"SEELE_"+safe, "namespace":"seele_"+item["transferId"].replace("-","")[:8], "nodesCreated":1, "createdNodes":[], "warnings":[]}
    def rollback(self, result): return True

def get_importer():
    try:
        import maya.cmds as cmds
        return MayaImporter(cmds)
    except ImportError:
        return MockImporter()

class MayaImporter(object):
    def __init__(self, cmds): self.cmds=cmds; self.probe=ReadinessProbe(cmds)
    def readiness(self,format_name=None,refresh=False):
        return self.probe.probe(format_name,refresh=refresh) if format_name else self.probe.all(refresh=refresh)
    def runtime(self): return {"version":str(self.cmds.about(version=True)),"platform":platform.system().lower()}
    def _invoke_import(self,path,format_name,namespace,before):
        spec=format_spec(format_name); handler=spec["handler"]
        if handler=="abc":
            self.cmds.namespace(setNamespace=namespace); self.cmds.AbcImport(path,mode="import")
            return list(snapshot.diff(self.cmds,before)["createdNodes"])
        if handler=="file":
            return self.cmds.file(path,i=True,type=spec["translators"][0],namespace=namespace,returnNewNodes=True,mergeNamespacesOnClash=False,executeScriptNodes=False) or []
        raise RuntimeError("IMPORT_SURFACE_UNAVAILABLE")
    def _restore_or_rollback(self,before,namespace):
        try:
            snapshot.restore_environment(self.cmds,before)
        except Exception:
            delta=snapshot.diff(self.cmds,before)
            try:
                self.rollback({"createdUuids":delta["createdUuids"],"createdReferences":delta["createdReferences"],"snapshot":before,"namespace":namespace})
            except snapshot.RollbackError:
                raise
            except Exception:
                raise snapshot.RollbackError("ROLLBACK_FAILED")
            raise
    def import_transfer(self, item, root):
        manifest=item["manifest"]
        format_name=manifest["target"]["format"]; ready=self.readiness(format_name,refresh=True)
        if not ready["ready"]: raise RuntimeError(ready["reason"])
        model=next(f for f in manifest["files"] if f["id"]==manifest["entryFileId"])
        path=os.path.abspath(os.path.join(root,"files",model["path"]))
        ns="seele_"+item["transferId"].replace("-","")[:8]; before=snapshot.capture(self.cmds); nodes=[]; group=None
        try:
            if not self.cmds.namespace(exists=ns): self.cmds.namespace(add=ns)
            nodes=self._invoke_import(path,format_name,ns,before)
            if not nodes: raise RuntimeError("IMPORT_CREATED_NO_NODES")
            node_set=set(nodes); tops=[]
            for node in nodes:
                if self.cmds.objExists(node) and self.cmds.nodeType(node)=="transform":
                    parent=self.cmds.listRelatives(node,parent=True,fullPath=True) or []
                    if not parent or parent[0] not in node_set: tops.append(node)
            safe="".join(c if c.isalnum() or c=="_" else "_" for c in (manifest.get("displayName") or "asset"))
            group=self.cmds.group(empty=True, name="SEELE_"+safe)
            for node in tops: self.cmds.parent(node,group)
            for name,value in (("seeleTransferId",item["transferId"]),("seeleReceiverVersion",__version__),("seeleCanvasId",manifest.get("canvasId", "")),("seeleSourceFormat",format_name)):
                self.cmds.addAttr(group,longName=name,dataType="string"); self.cmds.setAttr(group+"."+name,value,type="string")
            delta=snapshot.diff(self.cmds,before)
            return {"group":group,"namespace":ns,"nodesCreated":len(delta["createdUuids"]),"createdUuids":delta["createdUuids"],"createdReferences":delta["createdReferences"],"snapshot":before,"warnings":[]}
        except Exception:
            delta=snapshot.diff(self.cmds,before); self.rollback({"createdUuids":delta["createdUuids"],"createdReferences":delta["createdReferences"],"snapshot":before,"namespace":ns})
            raise
        finally:
            self._restore_or_rollback(before,ns)
    def rollback(self,result):
        return snapshot.rollback(self.cmds,result)
