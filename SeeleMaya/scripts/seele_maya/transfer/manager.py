import threading, time
from ..contract.models import digest_manifest
from .staging import staging_root
from .downloader import download_file
from ..maya_api.importer import get_importer
from ..maya_api.main_thread import execute

TRANSITIONS={"accepted":("downloading", "cancelled"), "downloading":("verifying", "cancelled"), "verifying":("queued", "cancelled"), "queued":("importing_geometry", "cancelled"), "importing_geometry":("organizing_scene", "cancel_pending"), "organizing_scene":("completed", "cancel_pending")}
TERMINAL=set(("completed", "completed_with_warnings", "failed", "cancelled"))
class TransferManager:
    def __init__(self): self.items={}; self.lock=threading.RLock(); self.importer=get_importer()
    def accept(self, manifest):
        tid=manifest["transferId"]; dg=digest_manifest(manifest)
        with self.lock:
            old=self.items.get(tid)
            if old:
                if old["digest"]!=dg: raise ValueError("TRANSFER_CONFLICT")
                return old
            now=time.time(); item={"transferId":tid,"manifest":manifest,"digest":dg,"state":"accepted","createdAt":now,"updatedAt":now,"cancel":threading.Event(),"warnings":[]}; self.items[tid]=item
            threading.Thread(target=self._run, args=(tid,), daemon=True).start(); return item
    def transition(self, tid, state):
        with self.lock:
            item=self.items[tid]; item["state"]=state; item["updatedAt"]=time.time(); return item
    def get(self, tid): return self.items.get(tid)
    def cancel(self, tid):
        item=self.items.get(tid)
        if not item: return None
        if item["state"] in TERMINAL: return item
        item["cancel"].set()
        if item["state"] in ("importing_geometry", "organizing_scene"): self.transition(tid,"cancel_pending")
        return item
    def _run(self, tid):
        item=self.items[tid]; root=staging_root(tid)
        try:
            self.transition(tid,"downloading")
            for spec in item["manifest"]["files"]: download_file(spec,root,item["cancel"])
            self.transition(tid,"verifying"); self.transition(tid,"queued")
            if item["cancel"].is_set(): return self.transition(tid,"cancelled")
            self.transition(tid,"importing_geometry")
            result=execute(lambda: self.importer.import_transfer(item,root)); item["result"]=result
            self.transition(tid,"organizing_scene"); self.transition(tid,"completed")
        except ValueError as exc:
            self.transition(tid,"cancelled" if str(exc)=="CANCELLED" else "failed"); item["error"]={"code":str(exc),"stage":"download","retryable":False}
        except Exception as exc:
            self.transition(tid,"failed"); item["error"]={"code":str(exc),"stage":"import","retryable":False}
