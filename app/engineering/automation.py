from dataclasses import dataclass,field
from datetime import datetime,timezone,timedelta
import uuid
@dataclass
class ScheduledTask:
 id:str; user_id:int; name:str; command:str; interval_seconds:int; enabled:bool=True; next_run:datetime=field(default_factory=lambda:datetime.now(timezone.utc))
@dataclass
class TaskRun:
 task_id:str; started_at:datetime; finished_at:datetime|None=None; status:str='running'; result:dict|None=None
class TaskScheduler:
 def __init__(self): self.tasks={}; self.history=[]
 def add(self,user_id,name,command,interval_seconds):
  t=ScheduledTask(str(uuid.uuid4()),user_id,name,command,interval_seconds); self.tasks[t.id]=t; return t
 def due(self,now=None):
  now=now or datetime.now(timezone.utc); return [t for t in self.tasks.values() if t.enabled and t.next_run<=now]
 def mark_run(self,t,result,status='success'):
  now=datetime.now(timezone.utc); r=TaskRun(t.id,now,now,status,result); self.history.append(r); t.next_run=now+timedelta(seconds=t.interval_seconds); return r
 def disable(self,task_id): self.tasks[task_id].enabled=False
