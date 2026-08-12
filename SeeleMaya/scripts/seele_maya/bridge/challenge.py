import secrets, time

class ChallengeStore:
    def __init__(self, ttl=60): self.ttl=ttl; self._items={}
    def issue(self, receiver_id, origin):
        token=secrets.token_urlsafe(24); self._items[token]=(receiver_id, origin, time.time()+self.ttl, False); return token, self._items[token][2]
    def consume(self, token, receiver_id, origin):
        item=self._items.get(token)
        if not item or item[0]!=receiver_id or item[1]!=origin: return "CHALLENGE_INVALID"
        if item[3]: return "CHALLENGE_REPLAYED"
        if time.time()>item[2]: return "CHALLENGE_EXPIRED"
        self._items[token]=(item[0],item[1],item[2],True); return None
