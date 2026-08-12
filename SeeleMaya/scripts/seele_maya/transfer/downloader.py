import hashlib, os
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler
from .staging import safe_path
from ..config import ALLOWED_DOWNLOAD_HOSTS, MAX_TOTAL_BYTES

def _allowed(url):
    p=urlparse(url)
    if p.scheme != "https" or p.username or p.password or p.fragment or not p.hostname:
        return False
    host=p.hostname.lower()
    return any(host == h or host.endswith("."+h) for h in ALLOWED_DOWNLOAD_HOSTS)

class SafeRedirect(HTTPRedirectHandler):
    max_redirections=4
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _allowed(newurl): raise ValueError("REDIRECT_NOT_ALLOWED")
        return HTTPRedirectHandler.redirect_request(self,req,fp,code,msg,headers,newurl)

def download_file(spec, root, cancel_event):
    url=spec.get("downloadUrl")
    if not _allowed(url): raise ValueError("URL_NOT_ALLOWED")
    target=safe_path(root, spec["path"]); part=target+".part"; total=0; digest=hashlib.sha256()
    try:
        opener=build_opener(SafeRedirect())
        with opener.open(Request(url, headers={"User-Agent":"SEELE-Maya/0.1"}), timeout=30) as response, open(part,"wb") as out:
            while True:
                if cancel_event.is_set(): raise ValueError("CANCELLED")
                chunk=response.read(1024*1024)
                if not chunk: break
                total += len(chunk)
                if total > MAX_TOTAL_BYTES or (spec.get("sizeBytes") is not None and total > int(spec["sizeBytes"])): raise ValueError("SIZE_LIMIT_EXCEEDED")
                digest.update(chunk); out.write(chunk)
        if spec.get("sizeBytes") is not None and total != int(spec["sizeBytes"]): raise ValueError("SIZE_MISMATCH")
        if spec.get("sha256") and digest.hexdigest() != spec["sha256"]: raise ValueError("HASH_MISMATCH")
        os.replace(part,target); return target
    except Exception:
        try: os.remove(part)
        except OSError: pass
        raise
