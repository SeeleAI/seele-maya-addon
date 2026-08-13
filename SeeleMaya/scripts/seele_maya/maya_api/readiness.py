import threading, time
from ..config import READINESS_CACHE_SECONDS
from ..formats import FORMAT_SPECS, format_spec

class ReadinessProbe(object):
    def __init__(self,cmds,ttl=READINESS_CACHE_SECONDS): self.cmds=cmds; self.ttl=ttl; self.lock=threading.RLock(); self.cache={}
    def invalidate(self,format_name=None):
        with self.lock:
            if format_name is None: self.cache.clear()
            else: self.cache.pop(format_name,None)
    def probe(self,format_name,load=True,refresh=False):
        now=time.monotonic()
        with self.lock:
            cached=self.cache.get(format_name)
            if cached and not refresh and cached[0]>now: return dict(cached[1])
        result=self._probe(format_name,load)
        with self.lock: self.cache[format_name]=(now+self.ttl,result)
        return dict(result)
    def all(self,load=True,refresh=False): return {name:self.probe(name,load,refresh) for name in FORMAT_SPECS}
    def _probe(self,format_name,load):
        spec=format_spec(format_name); unavailable=format_name.upper()+"_IMPORTER_UNAVAILABLE"
        try:
            for plugin in spec.get("plugins",()):
                loaded=bool(self.cmds.pluginInfo(plugin,query=True,loaded=True))
                if not loaded and load: self.cmds.loadPlugin(plugin,quiet=True); loaded=bool(self.cmds.pluginInfo(plugin,query=True,loaded=True))
                if not loaded: return {"ready":False,"provider":spec["provider"],"reason":format_name.upper()+"_PLUGIN_UNAVAILABLE"}
            if not spec.get("handler") or spec.get("import_surface_verified") is False: return {"ready":False,"provider":spec["provider"],"reason":format_name.upper()+"_IMPORT_SURFACE_UNAVAILABLE"}
            translators=set(self.cmds.translator(query=True,list=True) or [])
            for translator in spec.get("translators",()):
                if translator not in translators: return {"ready":False,"provider":spec["provider"],"reason":format_name.upper()+"_TRANSLATOR_UNAVAILABLE"}
                try: self.cmds.translator(translator,query=True,loaded=True)
                except Exception: return {"ready":False,"provider":spec["provider"],"reason":format_name.upper()+"_TRANSLATOR_UNAVAILABLE"}
            for command in spec.get("commands",()):
                try: callable_command=callable(getattr(self.cmds,command))
                except Exception: callable_command=False
                if not callable_command: return {"ready":False,"provider":spec["provider"],"reason":format_name.upper()+"_COMMAND_UNAVAILABLE"}
            result={"ready":True,"provider":spec["provider"],"reason":None,"handler":spec["handler"]}
            if spec.get("translators"): result["translator"]=spec["translators"][0]
            if spec.get("commands"): result["command"]=spec["commands"][0]
            return result
        except Exception: return {"ready":False,"provider":spec["provider"],"reason":unavailable}
