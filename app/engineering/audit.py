from dataclasses import dataclass,asdict
from datetime import datetime,timezone
import json, uuid

def utcnow(): return datetime.now(timezone.utc).isoformat()
@dataclass
class AuditEntry:
 user_request:str; ai_decision:str; tool:str; repository:str|None; target:str|None; action:str; result:str; timestamp:str; operation_id:str
class AuditLog:
 def __init__(self): self.entries=[]
 def record(self,**kw):
  e=AuditEntry(timestamp=utcnow(),operation_id=kw.pop('operation_id',str(uuid.uuid4())),**kw); self.entries.append(e); return e
 def export_json(self): return json.dumps([asdict(x) for x in self.entries],indent=2)
