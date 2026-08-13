import os
import platform
from ..formats import FORMAT_SPECS, format_spec

class MockImporter(object):
    def readiness(self,format_name=None):
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
    def __init__(self, cmds): self.cmds=cmds
    def readiness(self,format_name=None):
        if format_name is None: return {name:self.readiness(name) for name in FORMAT_SPECS}
        spec=format_spec(format_name); reason=format_name.upper()+"_IMPORTER_UNAVAILABLE"
        try:
            for plugin in spec.get("plugins",()):
                if not self.cmds.pluginInfo(plugin,query=True,loaded=True): self.cmds.loadPlugin(plugin,quiet=True)
                if not self.cmds.pluginInfo(plugin,query=True,loaded=True): return {"ready":False,"provider":spec["provider"],"reason":format_name.upper()+"_PLUGIN_UNAVAILABLE"}
            if spec.get("import_surface_verified") is False:
                return {"ready":False,"provider":spec["provider"],"reason":format_name.upper()+"_IMPORT_SURFACE_UNAVAILABLE"}
            translators=set(self.cmds.translator(query=True,list=True) or [])
            for translator in spec.get("translators",()):
                if translator not in translators: return {"ready":False,"provider":spec["provider"],"reason":format_name.upper()+"_TRANSLATOR_UNAVAILABLE"}
            for command in spec.get("commands",()):
                if not hasattr(self.cmds,command): return {"ready":False,"provider":spec["provider"],"reason":format_name.upper()+"_COMMAND_UNAVAILABLE"}
            result={"ready":True,"provider":spec["provider"],"reason":None}
            if spec.get("translators"): result["translator"]=spec["translators"][0]
            if spec.get("commands"): result["command"]=spec["commands"][0]
            return result
        except Exception:
            return {"ready":False,"provider":spec["provider"],"reason":reason}
    def runtime(self): return {"version":str(self.cmds.about(version=True)),"platform":platform.system().lower()}
    def import_transfer(self, item, root):
        manifest=item["manifest"]
        format_name=manifest["target"]["format"]; ready=self.readiness(format_name)
        if not ready["ready"]: raise RuntimeError(ready["reason"])
        model=next(f for f in manifest["files"] if f["id"]==manifest["entryFileId"])
        path=os.path.abspath(os.path.join(root,"files",model["path"]))
        ns="seele_"+item["transferId"].replace("-","")[:8]; old_selection=self.cmds.ls(selection=True,long=True) or []; old_ns=self.cmds.namespaceInfo(currentNamespace=True); nodes=[]; group=None
        try:
            if format_name=="abc":
                before=set(self.cmds.ls(long=True) or []); self.cmds.AbcImport(path,mode="import"); nodes=list(set(self.cmds.ls(long=True) or [])-before)
            else:
                translator=format_spec(format_name)["translators"][0]
                nodes=self.cmds.file(path,i=True,type=translator,namespace=ns,returnNewNodes=True,mergeNamespacesOnClash=False,executeScriptNodes=False) or []
            if not nodes: raise RuntimeError("IMPORT_CREATED_NO_NODES")
            node_set=set(nodes); tops=[]
            for node in nodes:
                if self.cmds.objExists(node) and self.cmds.nodeType(node)=="transform":
                    parent=self.cmds.listRelatives(node,parent=True,fullPath=True) or []
                    if not parent or parent[0] not in node_set: tops.append(node)
            safe="".join(c if c.isalnum() or c=="_" else "_" for c in (manifest.get("displayName") or "asset"))
            group=self.cmds.group(empty=True, name="SEELE_"+safe)
            for node in tops: self.cmds.parent(node,group)
            for name,value in (("seeleTransferId",item["transferId"]),("seeleReceiverVersion","0.2.0"),("seeleCanvasId",manifest.get("canvasId", "")),("seeleSourceFormat",format_name)):
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
