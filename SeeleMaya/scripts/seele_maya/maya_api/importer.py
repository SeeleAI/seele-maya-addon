import os

class MockImporter(object):
    def import_transfer(self, item, root):
        name=item["manifest"].get("displayName") or "asset"
        safe="".join(c if c.isalnum() or c in "_-" else "_" for c in name).strip("_") or "asset"
        return {"group":"SEELE_"+safe, "namespace":"seele_"+item["transferId"].replace("-","")[:8], "nodesCreated":1, "warnings":[]}

def get_importer():
    try:
        import maya.cmds as cmds
        return MayaImporter(cmds)
    except ImportError:
        return MockImporter()

class MayaImporter(object):
    def __init__(self, cmds): self.cmds=cmds
    def import_transfer(self, item, root):
        manifest=item["manifest"]
        model=next(f for f in manifest["files"] if f["id"]==manifest["entryFileId"])
        path=os.path.abspath(os.path.join(root,"files",model["path"]))
        if not self.cmds.pluginInfo("fbxmaya", query=True, loaded=True): self.cmds.loadPlugin("fbxmaya", quiet=True)
        ns="seele_"+item["transferId"].replace("-","")[:8]; old_selection=self.cmds.ls(selection=True,long=True) or []; old_ns=self.cmds.namespaceInfo(currentNamespace=True)
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
            return {"group":group,"namespace":ns,"nodesCreated":len(nodes),"warnings":[]}
        finally:
            try: self.cmds.namespace(setNamespace=old_ns)
            except Exception: pass
            try: self.cmds.select(old_selection,replace=True) if old_selection else self.cmds.select(clear=True)
            except Exception: pass
