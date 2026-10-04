from dataclasses import dataclass,field
from pathlib import PurePosixPath
import re

@dataclass
class RepoKnowledge:
 repository:str
 files:dict[str,str]=field(default_factory=dict)
 metadata:dict=field(default_factory=dict)
 symbols:dict[str,list[str]]=field(default_factory=dict)
 dependencies:dict[str,str]=field(default_factory=dict)
 def index(self, files):
  self.files={k:v for k,v in files.items() if not self._ignored(k)}
  for path,text in self.files.items():
   self.symbols[path]=self._symbols(text)
  self.dependencies=self._deps()
 def _ignored(self,p): return any(x in p for x in ('.git/','build/','.gradle/','node_modules/','__pycache__/'))
 def _symbols(self,t): return re.findall(r'\b(?:class|interface|object|fun|def|function)\s+([A-Za-z_][\w]*)',t)
 def search(self,q,limit=10):
  terms=[x.lower() for x in re.findall(r'[A-Za-z_][\w.-]+',q)]
  scored=[]
  for p,t in self.files.items():
   hay=(p+' '+t).lower(); score=sum(hay.count(x) for x in terms)
   if score: scored.append((score,p))
  return [p for _,p in sorted(scored,reverse=True)[:limit]]
 def locate(self,q): return self.search(q,10)
 def _deps(self):
  out={}
  for p,t in self.files.items():
   if p.endswith(('.gradle','.gradle.kts')):
    for n,v in re.findall(r'([A-Za-z0-9_.-]+)\s*[:=]\s*["\']([^"\']+)',t): out[n]=v
   if p.endswith('requirements.txt'):
    for line in t.splitlines():
     m=re.match(r'([A-Za-z0-9_.-]+)(?:==|>=|~=)?\s*([\w.*+-]*)',line.strip())
     if m: out[m.group(1)]=m.group(2)
  return out
