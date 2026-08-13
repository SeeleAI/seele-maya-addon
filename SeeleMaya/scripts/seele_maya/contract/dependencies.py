import os, re, shlex
from .validator import ContractError, _validate_path

MAX_TEXT_BYTES=16*1024*1024
MAX_LINES=200000
MAX_LINE_BYTES=16*1024
MAP_DIRECTIVES=frozenset(("map_ka","map_kd","map_ks","map_ke","map_d","bump","map_bump","disp","decal","norm","map_pr","map_pm","map_ps"))

def _dependency(base_path,value):
    value=value.strip().strip('"')
    if not value or "%" in value or "\\" in value or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:",value) or "?" in value or "#" in value: raise ContractError("PATH_UNSAFE","unsafe dependency path")
    combined=os.path.normpath(os.path.join(os.path.dirname(base_path),value)).replace("\\","/"); _validate_path(combined); return combined

def _lines(path):
    if os.path.getsize(path)>MAX_TEXT_BYTES: raise ContractError("DEPENDENCY_UNSUPPORTED","dependency text is too large")
    with open(path,"rb") as stream:
        for number,raw in enumerate(stream,1):
            if number>MAX_LINES or len(raw)>MAX_LINE_BYTES: raise ContractError("DEPENDENCY_UNSUPPORTED","dependency text exceeds limits")
            if b"\x00" in raw: raise ContractError("PATH_UNSAFE","dependency contains NUL")
            try: yield raw.decode("utf-8-sig").strip()
            except UnicodeDecodeError: yield raw.decode("latin-1").strip()

def _tokens(line):
    try: return shlex.split(line,comments=True,posix=True)
    except ValueError: raise ContractError("DEPENDENCY_UNSUPPORTED","dependency syntax is invalid")

def validate_obj_closure(root,manifest):
    by_path={f["path"]:f for f in manifest["files"]}; entry=next(f for f in manifest["files"] if f["id"]==manifest["entryFileId"]); obj_path=os.path.join(root,"files",*entry["path"].split("/")); mtls=[]; textures=[]
    for line in _lines(obj_path):
        if not line or line.startswith("#"): continue
        parts=_tokens(line)
        if parts and parts[0].lower()=="mtllib":
            for value in parts[1:]: mtls.append(_dependency(entry["path"],value))
    if len(mtls)>32: raise ContractError("DEPENDENCY_UNSUPPORTED","too many OBJ material libraries")
    for rel in mtls:
        spec=by_path.get(rel)
        if not spec or spec.get("kind")!="AUXILIARY" or spec.get("format")!="mtl": raise ContractError("DEPENDENCY_MISSING","OBJ material dependency is missing")
        path=os.path.join(root,"files",*rel.split("/"))
        for line in _lines(path):
            if not line or line.startswith("#"): continue
            parts=_tokens(line)
            if parts and parts[0].lower() in MAP_DIRECTIVES and len(parts)>1:
                # Map options are deliberately unsupported until tokenized unambiguously.
                value=" ".join(parts[1:]).strip()
                if value.startswith("-"): raise ContractError("DEPENDENCY_UNSUPPORTED","MTL map options are unsupported")
                textures.append(_dependency(rel,value))
    if len(textures)>96: raise ContractError("DEPENDENCY_UNSUPPORTED","too many OBJ textures")
    for rel in textures:
        spec=by_path.get(rel)
        if not spec or spec.get("kind")!="TEXTURE": raise ContractError("DEPENDENCY_MISSING","OBJ texture dependency is missing")
    return {"materials":mtls,"textures":textures}
