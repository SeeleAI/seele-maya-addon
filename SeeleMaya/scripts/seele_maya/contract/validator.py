import re
import uuid
import os
from datetime import datetime, timezone
from ..config import MAX_FILES, MAX_TOTAL_BYTES, MAX_MANIFEST_TTL_SECONDS
from ..formats import CONTENT_TYPES, FORMAT_SPECS, TEXTURE_EXTENSIONS, format_spec
from ..transfer.downloader import url_allowed

HEX64 = re.compile(r"^[0-9a-f]{64}$")
RFC3339 = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$")
KNOWN_TOP = set(("version", "transferId", "receiverId", "target", "canvasId", "displayName", "entryFileId", "coordinateSystem", "unitScaleMeters", "files", "materials", "limits", "createdAt", "expiresAt"))

class ContractError(ValueError):
    def __init__(self, code, message, stage="validation", retryable=False):
        super().__init__(message); self.code=code; self.stage=stage; self.retryable=retryable

def _time(value):
    try:
        if not isinstance(value,str) or not RFC3339.fullmatch(value): raise ValueError()
        parsed=datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None: raise ValueError()
        return parsed
    except Exception: raise ContractError("MANIFEST_INVALID", "invalid timestamp")

def _validate_path(value):
    if not isinstance(value, str) or not value or len(value)>1024 or "\x00" in value or any(ord(c)<32 for c in value): raise ContractError("PATH_UNSAFE", "unsafe manifest path")
    if "\\" in value or value.startswith(("/", "//")) or re.match(r"^[A-Za-z]:",value): raise ContractError("PATH_UNSAFE", "unsafe manifest path")
    parts=value.split("/")
    reserved=set(("CON","PRN","AUX","NUL","COM1","COM2","COM3","COM4","COM5","COM6","COM7","COM8","COM9","LPT1","LPT2","LPT3","LPT4","LPT5","LPT6","LPT7","LPT8","LPT9"))
    for part in parts:
        stem=part.split(".",1)[0].upper()
        if not part or part in (".","..") or len(part)>255 or part.endswith((" ",".")) or ":" in part or stem in reserved: raise ContractError("PATH_UNSAFE", "unsafe manifest path")

def validate_manifest(m, receiver_id, now=None):
    if not isinstance(m, dict) or any(k not in KNOWN_TOP for k in m):
        raise ContractError("MANIFEST_INVALID", "unknown or invalid manifest fields")
    if m.get("version") != "dcc-transfer.v1": raise ContractError("UNSUPPORTED_PROTOCOL", "manifest version is unsupported")
    if m.get("receiverId") != receiver_id: raise ContractError("RECEIVER_MISMATCH", "manifest receiverId mismatch")
    try: uuid.UUID(m["transferId"])
    except Exception: raise ContractError("MANIFEST_INVALID", "transferId must be UUID")
    target=m.get("target") or {}; target_format=target.get("format")
    if target.get("dcc") != "maya": raise ContractError("UNSUPPORTED_TARGET", "target DCC must be Maya")
    if target_format not in FORMAT_SPECS: raise ContractError("UNSUPPORTED_FORMAT", "target format is unsupported")
    files=m.get("files")
    if not isinstance(files, list) or not files: raise ContractError("MANIFEST_INVALID", "manifest.files is invalid")
    limits=m.get("limits") or {}
    if not isinstance(limits,dict): raise ContractError("MANIFEST_INVALID", "manifest.limits is invalid")
    try: max_files=min(int(limits.get("maxFiles",MAX_FILES)),MAX_FILES); max_bytes=min(int(limits.get("maxTotalBytes",MAX_TOTAL_BYTES)),MAX_TOTAL_BYTES)
    except (TypeError,ValueError): raise ContractError("MANIFEST_INVALID", "manifest.limits is invalid")
    if max_files<1 or max_bytes<0: raise ContractError("MANIFEST_INVALID", "manifest.limits is invalid")
    if len(files)>max_files: raise ContractError("FILE_LIMIT_EXCEEDED", "file count exceeds limit")
    ids=set(); paths=set(); total=0; model_ids=set()
    for f in files:
        if not isinstance(f, dict) or not isinstance(f.get("id"),str) or not f.get("id") or f.get("id") in ids or f.get("path") in paths: raise ContractError("MANIFEST_INVALID", "duplicate or invalid file")
        ids.add(f.get("id")); paths.add(f.get("path"))
        if f.get("kind") not in ("MODEL","AUXILIARY","TEXTURE"): raise ContractError("MANIFEST_INVALID","file kind is unsupported")
        p=f.get("path", ""); _validate_path(p)
        file_format=f.get("format"); extension=os.path.splitext(p)[1].lower()
        if file_format not in CONTENT_TYPES or f.get("contentType") not in CONTENT_TYPES[file_format]: raise ContractError("MANIFEST_INVALID","file contentType is invalid")
        if not isinstance(f.get("downloadUrl"),str) or not url_allowed(f["downloadUrl"]): raise ContractError("URL_NOT_ALLOWED","download URL is not allowed")
        size=f.get("sizeBytes")
        if not isinstance(size,int) or isinstance(size,bool) or size<0: raise ContractError("MANIFEST_INVALID", "sizeBytes is required")
        total += size
        if f.get("kind") == "MODEL":
            if f.get("format")!=target_format or os.path.splitext(p)[1].lower()!=format_spec(target_format)["extension"]: raise ContractError("UNSUPPORTED_FORMAT","entry model format is invalid")
            model_ids.add(f.get("id"))
        if not isinstance(f.get("sha256"),str) or not HEX64.match(f["sha256"]): raise ContractError("MANIFEST_INVALID", "sha256 is required")
    if m.get("entryFileId") not in model_ids: raise ContractError("MANIFEST_INVALID", "entryFileId must reference the model")
    if len(model_ids)!=1: raise ContractError("MANIFEST_INVALID","manifest must contain exactly one model")
    policy=format_spec(target_format)["policy"]
    if policy=="none" and len(files)!=1: raise ContractError("DEPENDENCY_UNSUPPORTED","format does not allow external dependencies")
    if policy=="obj_mtl_textures":
        allowed_aux=frozenset(("mtl",)); allowed_textures=frozenset(("png","jpg","jpeg","tga","tif","tiff","exr","bmp"))
        for f in files:
            if f["kind"]=="AUXILIARY" and (f.get("format") not in allowed_aux or os.path.splitext(f["path"])[1].lower()!=".mtl"): raise ContractError("DEPENDENCY_UNSUPPORTED","OBJ auxiliary format is unsupported")
            if f["kind"]=="TEXTURE" and (f.get("format") not in allowed_textures or os.path.splitext(f["path"])[1].lower()!=TEXTURE_EXTENSIONS[f.get("format")]): raise ContractError("DEPENDENCY_UNSUPPORTED","OBJ texture format is unsupported")
    if policy=="optional_textures":
        for f in files:
            if f["kind"] not in ("MODEL","TEXTURE"): raise ContractError("DEPENDENCY_UNSUPPORTED","FBX dependency kind is unsupported")
            if f["kind"]=="TEXTURE" and (f.get("format") not in TEXTURE_EXTENSIONS or os.path.splitext(f["path"])[1].lower()!=TEXTURE_EXTENSIONS[f.get("format")]): raise ContractError("DEPENDENCY_UNSUPPORTED","FBX texture format is unsupported")
    if total > max_bytes: raise ContractError("SIZE_LIMIT_EXCEEDED", "total size exceeds limit")
    created=_time(m.get("createdAt")); expires=_time(m.get("expiresAt")); now=now or datetime.now(timezone.utc)
    if expires <= now: raise ContractError("TRANSFER_EXPIRED", "manifest expired")
    if expires <= created or (expires-created).total_seconds()>MAX_MANIFEST_TTL_SECONDS: raise ContractError("MANIFEST_INVALID", "manifest TTL is invalid")
    return True
