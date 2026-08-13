import os, stat, shutil
from ..config import data_dir

def staging_root(transfer_id):
    data_root=os.path.realpath(data_dir())
    parent=os.path.join(data_root,"staging")
    os.makedirs(parent,mode=0o700,exist_ok=True)
    _assert_no_links(parent,data_root)
    base=os.path.join(parent,transfer_id)
    try: os.mkdir(base,0o700)
    except FileExistsError: raise ValueError("STAGING_CONFLICT")
    os.mkdir(os.path.join(base,"files"),0o700)
    return base

def _is_reparse(st): return bool(getattr(st,"st_file_attributes",0) & 0x400)
def _assert_no_links(path,boundary):
    current=os.path.abspath(path); boundary=os.path.abspath(boundary); parts=[]
    if os.path.commonpath((boundary,current))!=boundary: raise ValueError("PATH_UNSAFE")
    while True:
        parts.append(current); parent=os.path.dirname(current)
        if current==boundary: break
        if parent==current: raise ValueError("PATH_UNSAFE")
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
    parent=os.path.dirname(result); os.makedirs(parent,mode=0o700,exist_ok=True); _assert_no_links(parent,root)
    if os.path.lexists(result): _assert_no_links(result,root)
    return result

def open_part(path):
    current=os.path.dirname(os.path.abspath(path)); boundary=None
    while os.path.dirname(current)!=current:
        if os.path.basename(current)=="files": boundary=os.path.dirname(current); break
        current=os.path.dirname(current)
    if boundary is None: raise ValueError("PATH_UNSAFE")
    _assert_no_links(os.path.dirname(path),boundary)
    flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL
    if hasattr(os,"O_NOFOLLOW"): flags |= os.O_NOFOLLOW
    return os.fdopen(os.open(path,flags,0o600),"wb")

class _StagedFile(object):
    def __init__(self,root,relative):
        self.path=safe_path(root,relative); self.part=self.path+".part"; self.parent_fd=None; self.file=None; self.committed=False
    def __enter__(self):
        parent=os.path.dirname(self.path); leaf=os.path.basename(self.path)
        if os.name=="nt":
            from . import windows_staging
            self.parent_fd=windows_staging.open_parent(os.path.abspath(self.root),self.relative)
            self.file=windows_staging.create_part(self.parent_fd,leaf)
            return self
        supports_dir_fd=(os.name!="nt" and hasattr(os,"O_NOFOLLOW") and hasattr(os,"O_DIRECTORY"))
        if supports_dir_fd:
            root_fd=os.open(os.path.abspath(self.root),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            current_fd=root_fd
            try:
                components=["files"]+[value for value in os.path.dirname(self.relative).split("/") if value]
                for component in components:
                    next_fd=os.open(component,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=current_fd)
                    if current_fd!=root_fd: os.close(current_fd)
                    current_fd=next_fd
                self.parent_fd=current_fd
            finally:
                if root_fd!=self.parent_fd: os.close(root_fd)
            flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW
            self.file=os.fdopen(os.open(leaf+".part",flags,0o600,dir_fd=self.parent_fd),"wb")
        else: self.file=open_part(self.part)
        return self
    def write(self,value): return self.file.write(value)
    def commit(self):
        if os.name=="nt":
            from . import windows_staging
            windows_staging.rename_part(self.file,self.parent_fd,os.path.basename(self.path)); self.file.close(); self.file=None
        else:
            self.file.flush(); os.fsync(self.file.fileno()); self.file.close(); self.file=None
        if os.name=="nt":
            pass
        elif self.parent_fd is not None:
            leaf=os.path.basename(self.path); os.replace(leaf+".part",leaf,src_dir_fd=self.parent_fd,dst_dir_fd=self.parent_fd)
        else:
            _assert_no_links(os.path.dirname(self.path),os.path.dirname(os.path.dirname(self.path)))
            os.replace(self.part,self.path)
        self.committed=True
    def __exit__(self,exc_type,exc,tb):
        if self.file is not None: self.file.close()
        if not self.committed:
            try:
                if self.parent_fd is not None and os.name!="nt": os.unlink(os.path.basename(self.path)+".part",dir_fd=self.parent_fd)
                else: os.remove(self.part)
            except OSError: pass
        if self.parent_fd is not None:
            if os.name=="nt":
                from . import windows_staging
                windows_staging.close_handle(self.parent_fd)
            else: os.close(self.parent_fd)

def staged_file(root,relative):
    value=_StagedFile(root,relative); value.root=root; value.relative=relative; return value

def cleanup_staging(root):
    expected=os.path.abspath(os.path.join(os.path.realpath(data_dir()),"staging"))
    target=os.path.abspath(root)
    if os.path.commonpath((expected,target))!=expected or target==expected: raise ValueError("PATH_UNSAFE")
    if os.path.lexists(target):
        _assert_no_links(target,expected)
        shutil.rmtree(target)
