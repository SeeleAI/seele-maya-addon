import secrets, threading, time
from datetime import datetime, timezone

class ChallengeStore:
    def __init__(self, ttl=60): self.ttl=ttl; self._items={}; self._lock=threading.Lock()
    def issue(self, receiver_id, origin):
        token=secrets.token_urlsafe(24); expires=time.time()+self.ttl
        with self._lock:
            now=time.time(); self._items={key:value for key,value in self._items.items() if value[2]>=now}
            self._items[token]=(receiver_id, origin, expires, False)
        return token, datetime.fromtimestamp(expires,timezone.utc).isoformat().replace("+00:00","Z")
    def consume(self, token, receiver_id, origin):
        with self._lock:
            item=self._items.get(token)
            if not item or item[0]!=receiver_id or item[1]!=origin: return "CHALLENGE_INVALID"
            if item[3]: return "CHALLENGE_REPLAYED"
            if time.time()>item[2]: return "CHALLENGE_EXPIRED"
            self._items[token]=(item[0],item[1],item[2],True); return None
