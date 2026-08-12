import re
import uuid
from datetime import datetime
from ..config import MAX_FILES, MAX_TOTAL_BYTES

HEX64 = re.compile(r"^[0-9a-f]{64}$")
KNOWN_TOP = set(("version", "transferId", "receiverId", "target", "canvasId", "displayName", "entryFileId", "coordinateSystem", "unitScaleMeters", "files", "materials", "limits", "createdAt", "expiresAt"))

class ContractError(ValueError):
    def __init__(self, code, message, stage="validation", retryable=False):
        super().__init__(message); self.code=code; self.stage=stage; self.retryable=retryable

def _time(value):
    try: return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception: raise ContractError("MANIFEST_INVALID", "invalid timestamp")

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
    limits=m.get("limits") or {}; max_files=min(int(limits.get("maxFiles", MAX_FILES)), MAX_FILES); max_bytes=min(int(limits.get("maxTotalBytes", MAX_TOTAL_BYTES)), MAX_TOTAL_BYTES)
    if len(files)>max_files: raise ContractError("FILE_LIMIT_EXCEEDED", "file count exceeds limit")
    ids=set(); paths=set(); total=0; entry=None
    for f in files:
        if not isinstance(f, dict) or f.get("id") in ids or f.get("path") in paths: raise ContractError("MANIFEST_INVALID", "duplicate or invalid file")
        ids.add(f.get("id")); paths.add(f.get("path"))
        if f.get("format") != "fbx" and f.get("kind") == "MODEL": raise ContractError("UNSUPPORTED_FORMAT", "model must be FBX")
        p=f.get("path", "")
        if not p or p.startswith(('/', '\\')) or any(x in ("", ".", "..") for x in p.replace('\\','/').split('/')): raise ContractError("PATH_UNSAFE", "unsafe manifest path")
        size=f.get("sizeBytes");
        if size is not None: total += int(size)
        if f.get("kind") == "MODEL" and f.get("format") == "fbx": entry=f.get("id")
        if f.get("sha256") is not None and not HEX64.match(f["sha256"]): raise ContractError("MANIFEST_INVALID", "invalid sha256")
    if m.get("entryFileId") not in ids or m.get("entryFileId") != entry: raise ContractError("MANIFEST_INVALID", "entryFileId must reference the model")
    if total > max_bytes: raise ContractError("SIZE_LIMIT_EXCEEDED", "total size exceeds limit")
    if now is not None and _time(m.get("expiresAt")) <= now: raise ContractError("TRANSFER_EXPIRED", "manifest expired")
    return True
