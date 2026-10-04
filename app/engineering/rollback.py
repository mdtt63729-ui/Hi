from dataclasses import dataclass
@dataclass
class RestorePoint:
 repository:str; branch:str; sha:str; created_at:str; reason:str
class RollbackManager:
 def __init__(self): self.points=[]
 def create(self,repository,branch,sha,reason):
  from datetime import datetime,timezone
  p=RestorePoint(repository,branch,sha,datetime.now(timezone.utc).isoformat(),reason); self.points.append(p); return p
 def latest(self,repository,branch):
  x=[p for p in self.points if p.repository==repository and p.branch==branch]; return x[-1] if x else None
