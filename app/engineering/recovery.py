from dataclasses import dataclass
from datetime import datetime,timezone
@dataclass
class ActiveRun:
 run_id:int; repository:str; owner:str; name:str; branch:str; chat_id:int|None=None; message_id:int|None=None; mode:str='webhook'
class RecoveryManager:
 def __init__(self): self.active={}
 def register(self,r): self.active[r.run_id]=r
 def remove(self,run_id): self.active.pop(run_id,None)
 def recoverable(self): return list(self.active.values())
