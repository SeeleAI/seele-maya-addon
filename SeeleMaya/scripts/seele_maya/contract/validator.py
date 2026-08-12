import re
import uuid
from datetime import datetime, timezone
from ..config import MAX_FILES, MAX_TOTAL_BYTES, MAX_MANIFEST_TTL_SECONDS

HEX64 = re.compile(r"^[0-9a-f]{64}$")
KNOWN_TOP = set(("version", "transferId", "receiverId", "target", "canvasId", "displayName", "entryFileId", "coordinateSystem", "unitScaleMeters", "files", "materials", "limits", "createdAt", "expiresAt"))

class ContractError(ValueError):
    def __init__(self, code, message, stage="validation", retryable=False):
        super().__init__(message); self.code=code; self.stage=stage; self.retryable=retryable

def _time(value):
    try:
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
    target=m.get("target") or {}
    if target.get("dcc") != "maya" or target.get("format") != "fbx": raise ContractError("UNSUPPORTED_TARGET", "only maya/fbx is supported")
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
        if not isinstance(f, dict) or f.get("id") in ids or f.get("path") in paths: raise ContractError("MANIFEST_INVALID", "duplicate or invalid file")
        ids.add(f.get("id")); paths.add(f.get("path"))
        if f.get("format") != "fbx" and f.get("kind") == "MODEL": raise ContractError("UNSUPPORTED_FORMAT", "model must be FBX")
        p=f.get("path", ""); _validate_path(p)
        size=f.get("sizeBytes")
        if not isinstance(size,int) or isinstance(size,bool) or size<0: raise ContractError("MANIFEST_INVALID", "sizeBytes is required")
        total += size
        if f.get("kind") == "MODEL" and f.get("format") == "fbx": model_ids.add(f.get("id"))
        if not isinstance(f.get("sha256"),str) or not HEX64.match(f["sha256"]): raise ContractError("MANIFEST_INVALID", "sha256 is required")
    if m.get("entryFileId") not in model_ids: raise ContractError("MANIFEST_INVALID", "entryFileId must reference the model")
    if total > max_bytes: raise ContractError("SIZE_LIMIT_EXCEEDED", "total size exceeds limit")
    created=_time(m.get("createdAt")); expires=_time(m.get("expiresAt")); now=now or datetime.now(timezone.utc)
    if expires <= now: raise ContractError("TRANSFER_EXPIRED", "manifest expired")
    if expires <= created or (expires-created).total_seconds()>MAX_MANIFEST_TTL_SECONDS: raise ContractError("MANIFEST_INVALID", "manifest TTL is invalid")
    return True
