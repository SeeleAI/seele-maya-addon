"""Main-thread Maya scene snapshots and UUID-based ownership rollback."""

class RollbackError(RuntimeError):
    pass

def _node_uuid_map(cmds):
    result={}
    for node in cmds.ls(long=True) or []:
        try:
            values=cmds.ls(node,uuid=True) or []
            if values: result[values[0]]=node
        except Exception:
            continue
    return result

def capture(cmds):
    playback={}
    for key,flag in (("min","minTime"),("max","maxTime"),("ast","animationStartTime"),("aet","animationEndTime")):
        try: playback[key]=cmds.playbackOptions(query=True,**{flag:True})
        except Exception: pass
    try: namespaces=set(cmds.namespaceInfo(listOnlyNamespaces=True,recurse=True) or [])
    except Exception: namespaces=set()
    try: references=set(cmds.ls(type="reference",long=True) or [])
    except Exception: references=set()
    try: plugins=set(cmds.pluginInfo(query=True,listPlugins=True) or [])
    except Exception: plugins=set()
    try: render_layer=cmds.editRenderLayerGlobals(query=True,currentRenderLayer=True)
    except Exception: render_layer=None
    try: current_tool=cmds.currentCtx()
    except Exception: current_tool=None
    try: scene_modified=bool(cmds.file(query=True,modified=True))
    except Exception: scene_modified=None
    return {
        "nodes":_node_uuid_map(cmds),
        "selection":cmds.ls(selection=True,long=True) or [],
        "namespace":cmds.namespaceInfo(currentNamespace=True),
        "namespaces":namespaces,
        "references":references,
        "plugins":plugins,
        "renderLayer":render_layer,
        "currentTool":current_tool,
        "sceneModified":scene_modified,
        "time":cmds.currentTime(query=True),
        "playback":playback,
        "linearUnit":cmds.currentUnit(query=True,linear=True),
        "timeUnit":cmds.currentUnit(query=True,time=True),
        "upAxis":cmds.upAxis(query=True,axis=True),
    }

def diff(cmds,before):
    after=_node_uuid_map(cmds)
    created={key:value for key,value in after.items() if key not in before["nodes"]}
    try: references=set(cmds.ls(type="reference",long=True) or [])
    except Exception: references=set()
    return {"createdUuids":tuple(created),"createdNodes":tuple(created.values()),"createdReferences":tuple(references-before.get("references",set()))}

def restore_environment(cmds,before):
    cmds.namespace(setNamespace=before["namespace"])
    cmds.currentTime(before["time"],edit=True)
    for key,flag in (("min","minTime"),("max","maxTime"),("ast","animationStartTime"),("aet","animationEndTime")):
        if key in before["playback"]: cmds.playbackOptions(**{flag:before["playback"][key]})
    if cmds.currentUnit(query=True,linear=True)!=before["linearUnit"]: cmds.currentUnit(linear=before["linearUnit"])
    if cmds.currentUnit(query=True,time=True)!=before["timeUnit"]: cmds.currentUnit(time=before["timeUnit"])
    if cmds.upAxis(query=True,axis=True)!=before["upAxis"]: cmds.upAxis(axis=before["upAxis"],updateView=False)
    if before.get("renderLayer") is not None: cmds.editRenderLayerGlobals(currentRenderLayer=before["renderLayer"])
    if before.get("currentTool") is not None: cmds.setToolTo(before["currentTool"])
    if before.get("sceneModified") is not None: cmds.file(modified=before["sceneModified"])
    existing=[node for node in before["selection"] if cmds.objExists(node)]
    cmds.select(existing,replace=True) if existing else cmds.select(clear=True)

def rollback(cmds,result):
    before=result.get("snapshot") or {}; uuids=result.get("createdUuids") or ()
    failures=[]
    for reference in reversed(result.get("createdReferences") or ()):
        try:
            if cmds.objExists(reference): cmds.file(removeReference=True,referenceNode=reference)
        except Exception as exc: failures.append(str(exc))
    for node_uuid in reversed(uuids):
        try:
            nodes=cmds.ls(node_uuid,long=True) or []
            if nodes: cmds.delete(nodes)
        except Exception as exc: failures.append(str(exc))
    namespace=result.get("namespace")
    if namespace and namespace not in before.get("namespaces",set()):
        try:
            if cmds.namespace(exists=namespace): cmds.namespace(removeNamespace=namespace,mergeNamespaceWithRoot=False)
        except Exception as exc: failures.append(str(exc))
    try: restore_environment(cmds,before)
    except Exception as exc: failures.append(str(exc))
    remaining=[]
    for node_uuid in uuids:
        try:
            if cmds.ls(node_uuid,long=True): remaining.append(node_uuid)
        except Exception: remaining.append(node_uuid)
    for reference in result.get("createdReferences") or ():
        try:
            if cmds.objExists(reference): remaining.append(reference)
        except Exception: remaining.append(reference)
    if remaining: raise RollbackError("ROLLBACK_INCOMPLETE")
    if failures: raise RollbackError("ROLLBACK_FAILED")
    return True
