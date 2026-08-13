import json, threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from .challenge import ChallengeStore
from ..config import HOST, PORT, ALLOWED_ORIGINS, MAX_BODY_BYTES, receiver_id
from ..contract.validator import validate_manifest, ContractError
from ..transfer.manager import TransferManager
from ..maya_api.main_thread import execute
from ..config import MAX_HTTP_THREADS, REQUEST_TIMEOUT_SECONDS
from ..formats import FORMAT_SPECS

RECEIVER_ID=receiver_id(); challenges=ChallengeStore(); manager=TransferManager()
_server=None; _thread=None; _lock=threading.RLock(); _status={"running":False,"error":None}
def envelope(data=None, error=None): return {"ok": error is None, "data": data} if error is None else {"ok":False,"error":error}
class BoundedHTTPServer(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,*args,**kwargs):
        self._slots=threading.BoundedSemaphore(MAX_HTTP_THREADS); ThreadingHTTPServer.__init__(self,*args,**kwargs)
    def process_request(self,request,client_address):
        if not self._slots.acquire(False):
            body=json.dumps(envelope(error={"code":"SERVER_BUSY","message":"receiver is busy","retryable":True,"stage":"receiver"})).encode("utf-8")
            response=("HTTP/1.1 503 Service Unavailable\r\nContent-Type: application/json\r\nContent-Length: %d\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n" % len(body)).encode("ascii")+body
            try: request.sendall(response)
            finally: request.close()
            return
        try: ThreadingHTTPServer.process_request(self,request,client_address)
        except Exception: self._slots.release(); raise
    def process_request_thread(self,request,client_address):
        try: ThreadingHTTPServer.process_request_thread(self,request,client_address)
        finally: self._slots.release()
class Handler(BaseHTTPRequestHandler):
    def setup(self):
        BaseHTTPRequestHandler.setup(self); self.connection.settimeout(REQUEST_TIMEOUT_SECONDS)
    def _send(self, status, body, origin=None):
        raw=json.dumps(body).encode(); self.send_response(status); self.send_header("Content-Type","application/json"); self.send_header("Content-Length",str(len(raw))); self.send_header("Cache-Control","no-store"); self.send_header("Vary","Origin")
        if origin in ALLOWED_ORIGINS: self.send_header("Access-Control-Allow-Origin",origin)
        self.end_headers(); self.wfile.write(raw)
    def _origin_allowed(self, origin): return origin in ALLOWED_ORIGINS
    def _reject_origin(self, origin):
        self._send(403,envelope(error={"code":"ORIGIN_NOT_ALLOWED","message":"origin is not allowed","retryable":False,"stage":"security"}),None)
    def do_OPTIONS(self):
        origin=self.headers.get("Origin")
        if not self._origin_allowed(origin): return self._reject_origin(origin)
        self.send_response(204); self.send_header("Access-Control-Allow-Origin",origin); self.send_header("Vary","Origin"); self.send_header("Access-Control-Allow-Methods","GET, POST, OPTIONS"); self.send_header("Access-Control-Allow-Headers","Content-Type"); self.send_header("Cache-Control","no-store")
        if self.headers.get("Access-Control-Request-Private-Network","").lower()=="true": self.send_header("Access-Control-Allow-Private-Network","true")
        self.end_headers()
    def do_GET(self):
        origin=self.headers.get("Origin");
        if not self._origin_allowed(origin): return self._reject_origin(origin)
        if self.path=="/v1/health":
            token, exp=challenges.issue(RECEIVER_ID, origin)
            readiness=execute(manager.importer.readiness); formats=[name for name in FORMAT_SPECS if readiness[name]["ready"]]
            runtime=execute(manager.importer.runtime) if hasattr(manager.importer,"runtime") else {"version":None,"platform":None}
            data={"service":"seele-dcc-receiver","dcc":"maya","version":"0.2.0","receiverId":RECEIVER_ID,"challenge":token,"challengeExpiresAt":exp,"protocols":["dcc-transfer.v1"],"formats":formats,"capabilities":{"formats":formats,"supportsStatus":True,"supportsCancel":True,"supportsRetryImport":False,"importers":readiness},"maya":runtime}
            self._send(200, envelope(data), origin)
        elif self.path.startswith("/v1/transfers/"):
            item=manager.get(self.path.rsplit('/',1)[-1])
            if item: self._send(200,envelope(item),origin)
            else: self._send(404,envelope(error={"code":"TRANSFER_NOT_FOUND","message":"transfer not found","retryable":False,"stage":"routing"}),origin)
        else: self._send(404,envelope(error={"code":"NOT_FOUND","message":"not found","retryable":False,"stage":"routing"}),origin)
    def do_POST(self):
        origin=self.headers.get("Origin")
        if not self._origin_allowed(origin): return self._reject_origin(origin)
        if self.path.endswith("/cancel"):
            item=manager.cancel(self.path.split("/")[-2])
            if not item: self._send(404,envelope(error={"code":"TRANSFER_NOT_FOUND","message":"transfer not found","retryable":False,"stage":"routing"}),origin); return
            self._send(200 if item["state"] in ("completed","completed_with_warnings","failed","cancelled") else 202,envelope({"transferId":item["transferId"],"state":item["state"]}),origin); return
        try: length=int(self.headers.get("Content-Length","0"))
        except ValueError: return self._send(400,envelope(error={"code":"INVALID_REQUEST","message":"invalid Content-Length","retryable":False,"stage":"validation"}),origin)
        if length>MAX_BODY_BYTES: return self._send(413,envelope(error={"code":"BODY_TOO_LARGE","message":"request too large","retryable":False,"stage":"validation"}),origin)
        try: body=json.loads(self.rfile.read(length).decode())
        except Exception: return self._send(400,envelope(error={"code":"INVALID_JSON","message":"invalid JSON","retryable":False,"stage":"validation"}),origin)
        if self.path=="/v1/transfers":
            try:
                if not isinstance(body,dict) or body.get("version")!="dcc-transfer.v1": raise ContractError("UNSUPPORTED_PROTOCOL","envelope version is unsupported")
                if body.get("receiverId")!=RECEIVER_ID: raise ContractError("RECEIVER_MISMATCH","receiver mismatch")
                err=challenges.consume(body.get("challenge"),RECEIVER_ID,origin)
                if err: raise ContractError(err,err)
                validate_manifest(body.get("manifest"),RECEIVER_ID)
                target_format=body["manifest"]["target"]["format"]
                readiness=execute(lambda: manager.importer.readiness(target_format))
                if not readiness["ready"]: raise ContractError(readiness["reason"] or target_format.upper()+"_IMPORTER_UNAVAILABLE",target_format.upper()+" importer is unavailable","readiness")
                item=manager.accept(body["manifest"]); self._send(202,envelope({"transferId":item["transferId"],"state":item["state"],"createdAt":item["createdAt"],"updatedAt":item["updatedAt"]}),origin)
            except (ContractError,ValueError) as e:
                code=getattr(e,"code",None) or (str(e) if str(e).isupper() else "MANIFEST_INVALID")
                self._send(400,envelope(error={"code":code,"message":str(e) if isinstance(e,ContractError) else "transfer request is invalid","retryable":getattr(e,"retryable",False),"stage":getattr(e,"stage","validation")}),origin)
        else: self._send(404,envelope(error={"code":"NOT_FOUND","message":"not found","retryable":False,"stage":"routing"}),origin)
    def log_message(self,*args): pass

def start():
    global _server,_thread
    with _lock:
        if _server: return dict(_status)
        try:
            manager.start_accepting()
            _server=BoundedHTTPServer((HOST,PORT),Handler)
            _thread=threading.Thread(target=_server.serve_forever,name="SeeleReceiver",daemon=True); _thread.start(); _status.update(running=True,error=None)
        except OSError as exc:
            _server=None; _thread=None; _status.update(running=False,error="PORT_IN_USE" if getattr(exc,"errno",None) in (48,98,10048) else "RECEIVER_START_FAILED")
        return dict(_status)

def stop(timeout=5):
    global _server,_thread
    with _lock: server=_server; thread=_thread; _server=None; _thread=None
    if server: server.shutdown(); server.server_close()
    workers_stopped=manager.shutdown(timeout)
    if thread: thread.join(timeout)
    _status.update(running=False,error=None if workers_stopped else "WORKERS_STILL_RUNNING"); return dict(_status)

def status(): return dict(_status)
if __name__=='__main__':
    start()
    if _server: _thread.join()
