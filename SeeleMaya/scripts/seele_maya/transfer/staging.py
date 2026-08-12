import os, stat, shutil
from ..config import data_dir

def staging_root(transfer_id):
    parent=os.path.join(data_dir(),"staging")
    os.makedirs(parent,mode=0o700,exist_ok=True)
    _assert_no_links(parent)
    base=os.path.join(parent,transfer_id)
    try: os.mkdir(base,0o700)
    except FileExistsError: raise ValueError("STAGING_CONFLICT")
    os.mkdir(os.path.join(base,"files"),0o700)
    return base

def _is_reparse(st): return bool(getattr(st,"st_file_attributes",0) & 0x400)
def _assert_no_links(path):
    current=os.path.abspath(path); parts=[]
    while True:
        parts.append(current); parent=os.path.dirname(current)
        if parent==current: break
        current=parent
    for candidate in reversed(parts):
        if not os.path.exists(candidate): continue
        st=os.lstat(candidate)
        if stat.S_ISLNK(st.st_mode) or _is_reparse(st): raise ValueError("PATH_UNSAFE")

def safe_path(root, relative):
    rel=relative
    if not isinstance(rel,str) or not rel or "\\" in rel or rel.startswith("/") or ".." in rel.split("/"):
        raise ValueError("PATH_UNSAFE")
    result = os.path.abspath(os.path.join(root, "files", *rel.split("/")))
    if os.path.commonpath((os.path.abspath(root), result)) != os.path.abspath(root):
        raise ValueError("PATH_UNSAFE")
    parent=os.path.dirname(result); os.makedirs(parent,mode=0o700,exist_ok=True); _assert_no_links(parent)
    if os.path.lexists(result): _assert_no_links(result)
    return result

def open_part(path):
    _assert_no_links(os.path.dirname(path))
    flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL
    if hasattr(os,"O_NOFOLLOW"): flags |= os.O_NOFOLLOW
    return os.fdopen(os.open(path,flags,0o600),"wb")

def cleanup_staging(root):
    expected=os.path.abspath(os.path.join(data_dir(),"staging"))
    target=os.path.abspath(root)
    if os.path.commonpath((expected,target))!=expected or target==expected: raise ValueError("PATH_UNSAFE")
    if os.path.lexists(target):
        _assert_no_links(target)
        shutil.rmtree(target)
