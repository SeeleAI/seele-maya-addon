import copy, threading
from datetime import datetime, timezone
from ..contract.models import digest_manifest
from .staging import staging_root, cleanup_staging
from .downloader import download_file, ByteBudget
from ..config import MAX_TOTAL_BYTES, MAX_INFLIGHT_TRANSFERS
from ..maya_api.importer import get_importer
from ..maya_api.main_thread import execute

TRANSITIONS={"accepted":("downloading","cancelled","failed"),"downloading":("verifying","cancelled","failed"),"verifying":("queued","cancelled","failed"),"queued":("importing_geometry","cancelled","failed"),"importing_geometry":("organizing_scene","cancel_pending","failed"),"organizing_scene":("completed","completed_with_warnings","cancel_pending","failed"),"cancel_pending":("rollback","failed"),"rollback":("cancelled","failed")}
TERMINAL=set(("completed", "completed_with_warnings", "failed", "cancelled"))
PUBLIC_STATES=set(("accepted","downloading","verifying","queued","importing_geometry","organizing_scene","cancel_pending","completed","completed_with_warnings","failed","cancelled"))
def _now(): return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
def _safe_error(exc, default, stage):
    value=str(exc)
    code=value if value and value.replace("_","").isalnum() and value.upper()==value else default
    messages={"CANCELLED":"transfer cancelled","HASH_MISMATCH":"file hash mismatch","SIZE_MISMATCH":"file size mismatch","SIZE_LIMIT_EXCEEDED":"transfer size limit exceeded","URL_NOT_ALLOWED":"download URL is not allowed","REDIRECT_NOT_ALLOWED":"download redirect is not allowed","PATH_UNSAFE":"unsafe staging path","STAGING_CONFLICT":"staging directory already exists"}
    return {"code":code,"message":messages.get(code,"transfer failed"),"stage":stage,"retryable":False}
class TransferManager:
    def __init__(self): self.items={}; self.lock=threading.RLock(); self.importer=get_importer(); self.accepting=True; self.threads={}
    def start_accepting(self):
        with self.lock: self.accepting=True
    def accept(self, manifest):
        tid=manifest["transferId"]; dg=digest_manifest(manifest)
        with self.lock:
            if not self.accepting: raise ValueError("RECEIVER_STOPPING")
            old=self.items.get(tid)
            if old:
                if old["digest"]!=dg: raise ValueError("TRANSFER_CONFLICT")
                return old
            active=sum(1 for x in self.items.values() if x["state"] not in TERMINAL)
            if active>=MAX_INFLIGHT_TRANSFERS: raise ValueError("TOO_MANY_TRANSFERS")
            now=_now(); item={"transferId":tid,"manifest":manifest,"digest":dg,"state":"accepted","createdAt":now,"updatedAt":now,"cancel":threading.Event(),"warnings":[]}; self.items[tid]=item
            worker=threading.Thread(target=self._run,args=(tid,),name="SeeleTransfer-"+tid[:8],daemon=True); self.threads[tid]=worker; worker.start(); return item
    def transition(self, tid, state):
        with self.lock:
            item=self.items[tid]; current=item["state"]
            if state not in TRANSITIONS.get(current,()): raise ValueError("INVALID_STATE_TRANSITION")
            item["state"]=state; item["updatedAt"]=_now(); return item
    def get(self, tid):
        with self.lock:
            item=self.items.get(tid)
            if not item: return None
            snapshot=copy.deepcopy({k:v for k,v in item.items() if k not in ("manifest","digest","cancel","importResult")})
            if snapshot["state"] not in PUBLIC_STATES: snapshot["state"]="cancel_pending"
            return snapshot
    def cancel(self, tid):
        with self.lock:
            item=self.items.get(tid)
            if not item: return None
            if item["state"] in TERMINAL: return self.get(tid)
            item["cancel"].set()
            if item["state"] in ("importing_geometry","organizing_scene"): self.transition(tid,"cancel_pending")
            return self.get(tid)
    def shutdown(self, timeout=5):
        with self.lock:
            self.accepting=False
            workers=[]
            for tid,item in self.items.items():
                if item["state"] not in TERMINAL:
                    item["cancel"].set(); worker=self.threads.get(tid)
                    if worker: workers.append(worker)
        deadline=datetime.now(timezone.utc).timestamp()+timeout
        for worker in workers:
            remaining=max(0,deadline-datetime.now(timezone.utc).timestamp())
            if remaining<=0: break
            worker.join(remaining)
        return not any(worker.is_alive() for worker in workers)
    def _rollback_cancelled_import(self, tid, import_result):
        with self.lock:
            item=self.items[tid]
            if item["state"] not in ("cancel_pending","rollback"):
                self.transition(tid,"cancel_pending")
            if item["state"]=="cancel_pending": self.transition(tid,"rollback")
        execute(lambda: self.importer.rollback(import_result))
        with self.lock:
            if self.items[tid]["state"]=="rollback": self.transition(tid,"cancelled")
    def _finish_import(self, tid, import_result):
        item=self.items[tid]
        public_result={k:v for k,v in import_result.items() if k in ("group","namespace","nodesCreated","warnings")}
        with self.lock:
            item["result"]=public_result; item["importResult"]=import_result
            cancelled=item["cancel"].is_set() or item["state"]=="cancel_pending"
            if not cancelled and item["state"]=="importing_geometry": self.transition(tid,"organizing_scene")
        if cancelled:
            self._rollback_cancelled_import(tid,import_result); return
        with self.lock:
            cancelled=item["cancel"].is_set() or item["state"]=="cancel_pending"
            if not cancelled: self.transition(tid,"completed_with_warnings" if item["warnings"] else "completed")
        if cancelled: self._rollback_cancelled_import(tid,import_result)
    def _run(self, tid):
        item=self.items[tid]; root=None
        try:
            root=staging_root(tid)
            self.transition(tid,"downloading")
            budget=ByteBudget(MAX_TOTAL_BYTES); entry=item["manifest"]["entryFileId"]
            ordered=sorted(item["manifest"]["files"],key=lambda f: 0 if f["id"]==entry else 1)
            for spec in ordered:
                try: download_file(spec,root,item["cancel"],budget)
                except Exception as exc:
                    if spec["id"]==entry or str(exc)=="CANCELLED": raise
                    warning=_safe_error(exc,"DEPENDENCY_MISSING","download")
                    with self.lock: item["warnings"].append({"code":warning["code"],"message":warning["message"],"fileId":spec["id"]})
            self.transition(tid,"verifying"); self.transition(tid,"queued")
            if item["cancel"].is_set(): return self.transition(tid,"cancelled")
            self.transition(tid,"importing_geometry")
            import_result=execute(lambda: self.importer.import_transfer(item,root))
            self._finish_import(tid,import_result)
        except ValueError as exc:
            state=item["state"]
            if item["cancel"].is_set() and state=="cancel_pending":
                import_result=item.get("importResult")
                if import_result: self._rollback_cancelled_import(tid,import_result)
                else: self.transition(tid,"rollback"); self.transition(tid,"cancelled")
                target="cancelled"
            else:
                target="cancelled" if str(exc)=="CANCELLED" else "failed"; self.transition(tid,target)
            with self.lock: item["error"]=_safe_error(exc,"DOWNLOAD_FAILED","download")
            if root:
                try: cleanup_staging(root)
                except Exception: pass
        except Exception as exc:
            try:
                if 'import_result' in locals(): execute(lambda: self.importer.rollback(import_result))
            except Exception: pass
            if item["state"] not in TERMINAL: self.transition(tid,"failed")
            with self.lock: item["error"]=_safe_error(exc,"IMPORT_FAILED","import")
            if root:
                try: cleanup_staging(root)
                except Exception: pass
        finally:
            with self.lock:
                self.threads.pop(tid,None); item.pop("importResult",None)
