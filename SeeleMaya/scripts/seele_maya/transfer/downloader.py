import hashlib, ipaddress, os
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler
from .staging import safe_path, open_part
from ..config import ALLOWED_DOWNLOAD_HOSTS, MAX_TOTAL_BYTES

def url_allowed(url):
    p=urlparse(url)
    if p.scheme != "https" or p.username or p.password or p.fragment or not p.hostname:
        return False
    host=p.hostname.lower()
    try: ipaddress.ip_address(host); return False
    except ValueError: pass
    try:
        if p.port not in (None,443): return False
    except ValueError: return False
    return any(host == h or host.endswith("."+h) for h in ALLOWED_DOWNLOAD_HOSTS)

_allowed=url_allowed

class SafeRedirect(HTTPRedirectHandler):
    max_redirections=4
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not url_allowed(newurl): raise ValueError("REDIRECT_NOT_ALLOWED")
        return HTTPRedirectHandler.redirect_request(self,req,fp,code,msg,headers,newurl)

class ByteBudget(object):
    def __init__(self, maximum): self.maximum=maximum; self.used=0
    def add(self, amount):
        self.used += amount
        if self.used > self.maximum: raise ValueError("SIZE_LIMIT_EXCEEDED")

def download_file(spec, root, cancel_event, budget):
    url=spec.get("downloadUrl")
    if not url_allowed(url): raise ValueError("URL_NOT_ALLOWED")
    target=safe_path(root, spec["path"]); part=target+".part"; total=0; digest=hashlib.sha256()
    try:
        opener=build_opener(SafeRedirect())
        with opener.open(Request(url, headers={"User-Agent":"SEELE-Maya/0.1"}), timeout=30) as response, open_part(part) as out:
            while True:
                if cancel_event.is_set(): raise ValueError("CANCELLED")
                chunk=response.read(1024*1024)
                if not chunk: break
                total += len(chunk)
                budget.add(len(chunk))
                if total > int(spec["sizeBytes"]): raise ValueError("SIZE_LIMIT_EXCEEDED")
                digest.update(chunk); out.write(chunk)
        if total != int(spec["sizeBytes"]): raise ValueError("SIZE_MISMATCH")
        if digest.hexdigest() != spec["sha256"]: raise ValueError("HASH_MISMATCH")
        os.replace(part,target); return target
    except Exception:
        try: os.remove(part)
        except OSError: pass
        raise
