from dataclasses import dataclass,asdict
from time import perf_counter
from collections import Counter
import json,logging
log=logging.getLogger(__name__)
@dataclass
class Metric:
 name:str; duration_ms:float; ok:bool; tags:dict
class Telemetry:
 def __init__(self): self.metrics=[]; self.counts=Counter()
 def observe(self,name,started,ok=True,**tags):
  m=Metric(name,(perf_counter()-started)*1000,ok,tags); self.metrics.append(m); self.counts[(name,'ok' if ok else 'error')]+=1; return m
 def snapshot(self): return {'counts':{f'{a}:{b}':n for (a,b),n in self.counts.items()},'metrics':[asdict(x) for x in self.metrics[-500:]]}
 def json(self): return json.dumps(self.snapshot(),indent=2)
