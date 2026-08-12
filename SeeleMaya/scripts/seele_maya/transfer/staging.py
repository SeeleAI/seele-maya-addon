import os, tempfile

def staging_root(transfer_id):
    base = os.path.join(tempfile.gettempdir(), "Seele", "MayaTransfer", "staging", transfer_id)
    os.makedirs(os.path.join(base, "files"), exist_ok=True)
    return base

def safe_path(root, relative):
    rel = relative.replace("\\", "/")
    if not rel or rel.startswith("/") or ".." in rel.split("/"):
        raise ValueError("PATH_UNSAFE")
    result = os.path.abspath(os.path.join(root, "files", *rel.split("/")))
    if os.path.commonpath((os.path.abspath(root), result)) != os.path.abspath(root):
        raise ValueError("PATH_UNSAFE")
    os.makedirs(os.path.dirname(result), exist_ok=True)
    return result
