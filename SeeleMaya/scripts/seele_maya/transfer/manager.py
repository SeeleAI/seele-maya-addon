import copy, threading
from datetime import datetime, timezone
from ..contract.models import digest_manifest
from .staging import staging_root, cleanup_staging
from .downloader import download_file, ByteBudget
from ..config import MAX_TOTAL_BYTES, MAX_INFLIGHT_TRANSFERS
from ..maya_api.importer import get_importer
from ..maya_api.main_thread import execute
from ..contract.dependencies import validate_dependencies
from ..formats import format_spec

TRANSITIONS={"accepted":("downloading","cancelled","failed"),"downloading":("verifying","cancelled","failed"),"verifying":("queued","cancelled","failed"),"queued":("importing_geometry","cancelled","failed"),"importing_geometry":("organizing_scene","cancel_pending","failed"),"organizing_scene":("completed","completed_with_warnings","cancel_pending","failed"),"cancel_pending":("rollback","failed"),"rollback":("cancelled","failed")}
TERMINAL=set(("completed", "completed_with_warnings", "failed", "cancelled"))
PUBLIC_STATES=set(("accepted","downloading","verifying","queued","importing_geometry","organizing_scene","cancel_pending","completed","completed_with_warnings","failed","cancelled"))
def _now(): return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
def _safe_error(exc, default, stage):
    stable=frozenset(("CANCELLED","HASH_MISMATCH","SIZE_MISMATCH","SIZE_LIMIT_EXCEEDED","URL_NOT_ALLOWED","REDIRECT_NOT_ALLOWED","PATH_UNSAFE","STAGING_CONFLICT","STAGING_CLEANUP_FAILED","DEPENDENCY_MISSING","DEPENDENCY_UNSUPPORTED","FBX_PLUGIN_UNAVAILABLE","FBX_TRANSLATOR_UNAVAILABLE","OBJ_TRANSLATOR_UNAVAILABLE","ABC_PLUGIN_UNAVAILABLE","ABC_COMMAND_UNAVAILABLE","DAE_PLUGIN_UNAVAILABLE","DAE_TRANSLATOR_UNAVAILABLE","USD_PLUGIN_UNAVAILABLE","USDA_PLUGIN_UNAVAILABLE","USDC_PLUGIN_UNAVAILABLE","IMPORT_CREATED_NO_NODES","ROLLBACK_INCOMPLETE","ROLLBACK_FAILED","SERVER_BUSY","TOO_MANY_TRANSFERS","RECEIVER_STOPPING"))
    candidate=getattr(exc,"code",None) or str(exc); code=candidate if candidate in stable else default
    messages={"CANCELLED":"transfer cancelled","HASH_MISMATCH":"file hash mismatch","SIZE_MISMATCH":"file size mismatch","SIZE_LIMIT_EXCEEDED":"transfer size limit exceeded","URL_NOT_ALLOWED":"download URL is not allowed","REDIRECT_NOT_ALLOWED":"download redirect is not allowed","PATH_UNSAFE":"unsafe staging path","STAGING_CONFLICT":"staging directory already exists","DEPENDENCY_MISSING":"declared dependency is missing","DEPENDENCY_UNSUPPORTED":"dependency is unsupported"}
    return {"code":code,"message":messages.get(code,"transfer failed"),"stage":getattr(exc,"stage",stage),"retryable":getattr(exc,"retryable",False)}
class TransferManager:
    def __init__(self): self.items={}; self.lock=threading.RLock(); self.import_lock=threading.Lock(); self.importer=get_importer(); self.accepting=True; self.threads={}
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
        try: execute(lambda: self.importer.rollback(import_result))
        except Exception as exc:
            with self.lock:
                if self.items[tid]["state"]=="rollback": self.transition(tid,"failed")
                self.items[tid]["error"]=_safe_error(exc,"ROLLBACK_FAILED","rollback")
            return False
        with self.lock:
            if self.items[tid]["state"]=="rollback": self.transition(tid,"cancelled")
        return True
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
        item=self.items[tid]; root=None; cleanup=False
        try:
            root=staging_root(tid)
            self.transition(tid,"downloading")
            budget=ByteBudget(MAX_TOTAL_BYTES); entry=item["manifest"]["entryFileId"]
            ordered=sorted(item["manifest"]["files"],key=lambda f: 0 if f["id"]==entry else 1)
            for spec in ordered:
                try: download_file(spec,root,item["cancel"],budget)
                except Exception as exc:
                    target_format=item["manifest"]["target"]["format"]
                    fatal=frozenset(("CANCELLED","HASH_MISMATCH","SIZE_MISMATCH","SIZE_LIMIT_EXCEEDED","URL_NOT_ALLOWED","REDIRECT_NOT_ALLOWED","PATH_UNSAFE"))
                    if spec["id"]==entry or format_spec(target_format).get("dependency_fail_closed",True) or str(exc) in fatal: raise
                    warning=_safe_error(exc,"DEPENDENCY_MISSING","download")
                    with self.lock: item["warnings"].append({"code":warning["code"],"message":warning["message"],"fileId":spec["id"]})
            validate_dependencies(root,item["manifest"])
            self.transition(tid,"verifying"); self.transition(tid,"queued")
            if item["cancel"].is_set(): return self.transition(tid,"cancelled")
            self.transition(tid,"importing_geometry")
            with self.import_lock:
                target_format=item["manifest"]["target"]["format"]; readiness=execute(lambda: self.importer.readiness(target_format,refresh=True))
                if not readiness["ready"]: raise ValueError(readiness["reason"])
                import_result=execute(lambda: self.importer.import_transfer(item,root))
                self._finish_import(tid,import_result)
                cleanup=item["state"] in TERMINAL
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
            cleanup=True
        except Exception as exc:
            rollback_error=None
            try:
                if 'import_result' in locals(): execute(lambda: self.importer.rollback(import_result))
            except Exception as rollback_exc: rollback_error=rollback_exc
            if item["state"] not in TERMINAL: self.transition(tid,"failed")
            with self.lock: item["error"]=_safe_error(rollback_error,"ROLLBACK_FAILED","rollback") if rollback_error else _safe_error(exc,"IMPORT_FAILED","import")
            cleanup=True
        finally:
            if root and (cleanup or item["state"] in TERMINAL):
                try: cleanup_staging(root)
                except Exception as cleanup_exc:
                    with self.lock:
                        if item["state"] not in ("failed",):
                            if item["state"] in ("completed","completed_with_warnings","cancelled"): item["state"]="failed"; item["updatedAt"]=_now()
                        item["error"]=_safe_error(cleanup_exc,"STAGING_CLEANUP_FAILED","cleanup")
            with self.lock:
                self.threads.pop(tid,None); item.pop("importResult",None)
