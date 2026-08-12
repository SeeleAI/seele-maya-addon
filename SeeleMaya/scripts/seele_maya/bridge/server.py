import json
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from .challenge import ChallengeStore
from ..config import HOST, PORT, ALLOWED_ORIGINS, MAX_BODY_BYTES, receiver_id
from ..contract.validator import validate_manifest, ContractError
from ..transfer.manager import TransferManager

RECEIVER_ID=receiver_id(); challenges=ChallengeStore(); manager=TransferManager()
def envelope(data=None, error=None): return {"ok": error is None, "data": data} if error is None else {"ok":False,"error":error}
class Handler(BaseHTTPRequestHandler):
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
            data={"service":"seele-dcc-receiver","dcc":"maya","version":"0.1.0","receiverId":RECEIVER_ID,"challenge":token,"challengeExpiresAt":exp,"protocols":["dcc-transfer.v1"],"formats":["fbx"],"capabilities":{"formats":["fbx"],"supportsStatus":True,"supportsCancel":True}}
            self._send(200, envelope(data), origin)
        elif self.path.startswith("/v1/transfers/"):
            item=manager.get(self.path.rsplit('/',1)[-1]); self._send(200,envelope({k:v for k,v in item.items() if k not in ("manifest","digest","cancel")} if item else None),origin)
        else: self._send(404,envelope(error={"code":"NOT_FOUND","message":"not found","retryable":False,"stage":"routing"}),origin)
    def do_POST(self):
        origin=self.headers.get("Origin"); length=int(self.headers.get("Content-Length","0"));
        if not self._origin_allowed(origin): return self._reject_origin(origin)
        if length>MAX_BODY_BYTES: return self._send(413,envelope(error={"code":"BODY_TOO_LARGE","message":"request too large","retryable":False,"stage":"validation"}),origin)
        try: body=json.loads(self.rfile.read(length).decode())
        except Exception: return self._send(400,envelope(error={"code":"INVALID_JSON","message":"invalid JSON","retryable":False,"stage":"validation"}),origin)
        if self.path.endswith("/cancel"):
            item=manager.cancel(self.path.split("/")[-2]); self._send(202 if item and item["state"] not in ("completed","failed","cancelled") else 200, envelope({"transferId":item["transferId"],"state":item["state"]} if item else None), origin); return
        if self.path=="/v1/transfers":
            try:
                if body.get("receiverId")!=RECEIVER_ID: raise ContractError("RECEIVER_MISMATCH","receiver mismatch")
                err=challenges.consume(body.get("challenge"),RECEIVER_ID,origin)
                if err: raise ContractError(err,err)
                validate_manifest(body.get("manifest"),RECEIVER_ID)
                item=manager.accept(body["manifest"]); self._send(202,envelope({"transferId":item["transferId"],"state":item["state"],"createdAt":item["createdAt"],"updatedAt":item["updatedAt"]}),origin)
            except (ContractError,ValueError) as e: self._send(400,envelope(error={"code":getattr(e,"code",str(e)),"message":str(e),"retryable":False,"stage":"validation"}),origin)
        else: self._send(404,envelope(error={"code":"NOT_FOUND","message":"not found","retryable":False,"stage":"routing"}),origin)
    def log_message(self,*args): pass
if __name__=='__main__': ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()
