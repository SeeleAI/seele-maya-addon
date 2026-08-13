"""Single source of truth for accepted Maya transfer formats."""
FORMAT_SPECS = {
    "fbx":{"phase":"P0","provider":"fbxmaya","plugins":("fbxmaya",),"translators":("FBX",),"policy":"optional_textures","extension":".fbx"},
    "obj":{"phase":"P0","provider":"maya_obj_translator","plugins":(),"translators":("OBJ",),"policy":"obj_mtl_textures","extension":".obj"},
    "abc":{"phase":"P0","provider":"AbcImport","plugins":("AbcImport",),"commands":("AbcImport",),"policy":"none","extension":".abc"},
    "dae":{"phase":"P1","provider":"DAE_FBX","plugins":("fbxmaya",),"translators":("DAE_FBX",),"policy":"none","extension":".dae"},
    "usd":{"phase":"P1","provider":"mayaUsdPlugin","plugins":("mayaUsdPlugin",),"policy":"none","extension":".usd","import_surface_verified":False},
    "usda":{"alias_of":"usd","extension":".usda"},
    "usdc":{"alias_of":"usd","extension":".usdc"},
}
FORBIDDEN_FORMATS=frozenset(("glb","gltf","usdz","stl","ma","mb","3ds","ass"))
TEXTURE_EXTENSIONS={"png":".png","jpg":".jpg","jpeg":".jpeg","tga":".tga","tif":".tif","tiff":".tiff","exr":".exr","bmp":".bmp"}
CONTENT_TYPES={
    "fbx":frozenset(("application/octet-stream","application/vnd.autodesk.fbx")),
    "obj":frozenset(("text/plain","model/obj","application/octet-stream")),
    "abc":frozenset(("application/octet-stream","application/x-alembic")),
    "dae":frozenset(("model/vnd.collada+xml","application/xml","text/xml")),
    "usd":frozenset(("application/octet-stream","model/vnd.usd")),
    "usda":frozenset(("text/plain","model/vnd.usda")),
    "usdc":frozenset(("application/octet-stream","model/vnd.usdc")),
    "mtl":frozenset(("text/plain","application/octet-stream")),
    "png":frozenset(("image/png",)),"jpg":frozenset(("image/jpeg",)),"jpeg":frozenset(("image/jpeg",)),
    "tga":frozenset(("image/x-tga","image/tga","application/octet-stream")),"tif":frozenset(("image/tiff",)),"tiff":frozenset(("image/tiff",)),
    "exr":frozenset(("image/x-exr","application/octet-stream")),"bmp":frozenset(("image/bmp",)),
}

def resolve_format(name):
    seen=set(); current=name
    while current in FORMAT_SPECS and "alias_of" in FORMAT_SPECS[current]:
        if current in seen: raise ValueError("FORMAT_REGISTRY_INVALID")
        seen.add(current); current=FORMAT_SPECS[current]["alias_of"]
    return current

def format_spec(name):
    if name not in FORMAT_SPECS: return None
    base=dict(FORMAT_SPECS[resolve_format(name)]); base.update(FORMAT_SPECS[name]); base.pop("alias_of",None); return base

def validate_registry():
    extensions=set()
    for name in FORMAT_SPECS:
        spec=format_spec(name); extension=spec.get("extension")
        if not extension or extension in extensions: raise ValueError("FORMAT_REGISTRY_INVALID")
        extensions.add(extension)
    return True

validate_registry()
