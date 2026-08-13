import hashlib, http.client, ipaddress, socket, ssl
from urllib.parse import urljoin, urlparse
from .staging import staged_file
from ..config import ALLOWED_DOWNLOAD_HOSTS
from .. import __version__

MAX_REDIRECTS=4

def _canonical_host(value):
    try:
        host=value.rstrip(".").encode("idna").decode("ascii").lower()
        if not host or len(host)>253: return None
        return host
    except (UnicodeError,AttributeError): return None

def url_allowed(url):
    try: p=urlparse(url)
    except ValueError: return False
    if p.scheme != "https" or p.username or p.password or p.fragment or not p.hostname: return False
    host=_canonical_host(p.hostname)
    if host is None: return False
    try: ipaddress.ip_address(host); return False
    except ValueError: pass
    try:
        if p.port not in (None,443): return False
    except ValueError: return False
    allowed=tuple(_canonical_host(value) for value in ALLOWED_DOWNLOAD_HOSTS)
    return host in allowed

_allowed=url_allowed

def _public_addresses(host,port=443):
    addresses=[]
    try: records=socket.getaddrinfo(host,port,0,socket.SOCK_STREAM)
    except socket.gaierror: raise ValueError("DNS_RESOLUTION_FAILED")
    for record in records:
        value=record[4][0]
        try: address=ipaddress.ip_address(value)
        except ValueError: raise ValueError("DNS_ADDRESS_UNSAFE")
        if not address.is_global: raise ValueError("DNS_ADDRESS_UNSAFE")
        if value not in addresses: addresses.append(value)
    if not addresses: raise ValueError("DNS_RESOLUTION_FAILED")
    return tuple(addresses)

class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self,host,address,port=443,timeout=30):
        http.client.HTTPSConnection.__init__(self,host,port=port,timeout=timeout,context=ssl.create_default_context()); self._address=address
    def connect(self):
        raw=socket.create_connection((self._address,self.port),self.timeout,self.source_address)
        self.sock=self._context.wrap_socket(raw,server_hostname=self.host)

def _request(url):
    parsed=urlparse(url); host=_canonical_host(parsed.hostname); addresses=_public_addresses(host,parsed.port or 443)
    path=parsed.path or "/"
    if parsed.query: path += "?"+parsed.query
    last_error=None
    for address in addresses:
        connection=_PinnedHTTPSConnection(host,address,parsed.port or 443)
        try:
            connection.request("GET",path,headers={"Host":host,"User-Agent":"SEELE-Maya/"+__version__,"Accept-Encoding":"identity","Connection":"close"})
            return connection,connection.getresponse()
        except (OSError,ssl.SSLError,http.client.HTTPException) as exc:
            last_error=exc; connection.close()
    raise last_error or ValueError("DOWNLOAD_FAILED")

def _preflight_length(response,expected,budget):
    content_length=response.getheader("Content-Length")
    if content_length is None: return
    try: declared=int(content_length)
    except (TypeError,ValueError): raise ValueError("SIZE_MISMATCH")
    if declared<0 or declared!=expected: raise ValueError("SIZE_MISMATCH")
    if budget.used+declared>budget.maximum: raise ValueError("SIZE_LIMIT_EXCEEDED")

class ByteBudget(object):
    def __init__(self, maximum): self.maximum=maximum; self.used=0
    def add(self, amount):
        self.used += amount
        if self.used > self.maximum: raise ValueError("SIZE_LIMIT_EXCEEDED")

def download_file(spec, root, cancel_event, budget):
    url=spec.get("downloadUrl"); expected=int(spec["sizeBytes"])
    for redirect_count in range(MAX_REDIRECTS+1):
        if not url_allowed(url): raise ValueError("URL_NOT_ALLOWED" if redirect_count==0 else "REDIRECT_NOT_ALLOWED")
        connection,response=_request(url)
        try:
            if response.status in (301,302,303,307,308):
                if redirect_count>=MAX_REDIRECTS: raise ValueError("REDIRECT_LIMIT_EXCEEDED")
                location=response.getheader("Location")
                if not location: raise ValueError("REDIRECT_NOT_ALLOWED")
                url=urljoin(url,location); continue
            if response.status<200 or response.status>=300: raise ValueError("DOWNLOAD_HTTP_ERROR")
            _preflight_length(response,expected,budget)
            total=0; digest=hashlib.sha256()
            with staged_file(root,spec["path"]) as staged:
                while True:
                    if cancel_event.is_set(): raise ValueError("CANCELLED")
                    chunk=response.read(1024*1024)
                    if not chunk: break
                    total += len(chunk); budget.add(len(chunk))
                    if total>expected: raise ValueError("SIZE_LIMIT_EXCEEDED")
                    digest.update(chunk); staged.write(chunk)
                if total!=expected: raise ValueError("SIZE_MISMATCH")
                if digest.hexdigest()!=spec["sha256"]: raise ValueError("HASH_MISMATCH")
                staged.commit()
            return staged.path
        finally: connection.close()
    raise ValueError("REDIRECT_LIMIT_EXCEEDED")
