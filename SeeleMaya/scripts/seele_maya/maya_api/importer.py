import os

class MockImporter(object):
    def readiness(self): return {"ready":False,"provider":"mock","reason":"MAYA_UNAVAILABLE","mayaVersion":None,"platform":None}
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
    def __init__(self, cmds): self.cmds=cmds
    def readiness(self):
        import platform
        try:
            if not self.cmds.pluginInfo("fbxmaya",query=True,loaded=True): self.cmds.loadPlugin("fbxmaya",quiet=True)
            ready=bool(self.cmds.pluginInfo("fbxmaya",query=True,loaded=True))
            return {"ready":ready,"provider":"fbxmaya","reason":None if ready else "FBX_PLUGIN_UNAVAILABLE","mayaVersion":str(self.cmds.about(version=True)),"platform":platform.system().lower()}
        except Exception:
            return {"ready":False,"provider":"fbxmaya","reason":"FBX_PLUGIN_UNAVAILABLE","mayaVersion":str(self.cmds.about(version=True)),"platform":platform.system().lower()}
    def import_transfer(self, item, root):
        manifest=item["manifest"]
        model=next(f for f in manifest["files"] if f["id"]==manifest["entryFileId"])
        path=os.path.abspath(os.path.join(root,"files",model["path"]))
        if not self.cmds.pluginInfo("fbxmaya", query=True, loaded=True): self.cmds.loadPlugin("fbxmaya", quiet=True)
        ns="seele_"+item["transferId"].replace("-","")[:8]; old_selection=self.cmds.ls(selection=True,long=True) or []; old_ns=self.cmds.namespaceInfo(currentNamespace=True); nodes=[]; group=None
        try:
            nodes=self.cmds.file(path, i=True, type="FBX", namespace=ns, returnNewNodes=True, mergeNamespacesOnClash=False, executeScriptNodes=False) or []
            if not nodes: raise RuntimeError("IMPORT_CREATED_NO_NODES")
            node_set=set(nodes); tops=[]
            for node in nodes:
                if self.cmds.objExists(node) and self.cmds.nodeType(node)=="transform":
                    parent=self.cmds.listRelatives(node,parent=True,fullPath=True) or []
                    if not parent or parent[0] not in node_set: tops.append(node)
            safe="".join(c if c.isalnum() or c=="_" else "_" for c in (manifest.get("displayName") or "asset"))
            group=self.cmds.group(empty=True, name="SEELE_"+safe)
            for node in tops: self.cmds.parent(node,group)
            for name,value in (("seeleTransferId",item["transferId"]),("seeleReceiverVersion","0.1.0"),("seeleCanvasId",manifest.get("canvasId", ""))):
                self.cmds.addAttr(group,longName=name,dataType="string"); self.cmds.setAttr(group+"."+name,value,type="string")
            return {"group":group,"namespace":ns,"nodesCreated":len(nodes),"createdNodes":list(nodes)+[group],"warnings":[]}
        except Exception:
            created=list(nodes)
            if group: created.append(group)
            self.rollback({"createdNodes":created,"namespace":ns})
            raise
        finally:
            try: self.cmds.namespace(setNamespace=old_ns)
            except Exception: pass
            try: self.cmds.select(old_selection,replace=True) if old_selection else self.cmds.select(clear=True)
            except Exception: pass
    def rollback(self,result):
        nodes=result.get("createdNodes",[]) if result else []
        existing=[n for n in reversed(nodes) if self.cmds.objExists(n)]
        if existing: self.cmds.delete(existing)
        ns=result.get("namespace") if result else None
        if ns and self.cmds.namespace(exists=ns):
            try: self.cmds.namespace(removeNamespace=ns)
            except Exception: pass
        return True
