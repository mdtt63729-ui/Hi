from dataclasses import dataclass
from datetime import datetime,timezone
@dataclass
class MemoryItem:
 repository:str; key:str; value:str; updated_at:str
class RepositoryMemory:
 def __init__(self): self.items={}
 def set(self,repository,key,value):
  x=MemoryItem(repository,key,value,datetime.now(timezone.utc).isoformat()); self.items[(repository,key)]=x; return x
 def get(self,repository,key,default=None):
  x=self.items.get((repository,key)); return x.value if x else default
 def all(self,repository): return {k[1]:v.value for k,v in self.items.items() if k[0]==repository}
