from dataclasses import dataclass
import re
@dataclass
class ProposedChange:
 path:str; old:str; new:str; reason:str
class CodeFixEngine:
 def propose(self, category, message, files):
  changes=[]
  if category in ('gradle','dependency'):
   for p,t in files.items():
    if p.endswith(('.gradle','.gradle.kts')) and 'SNAPSHOT' in t:
     changes.append(ProposedChange(p,t,t.replace('-SNAPSHOT',''), 'Replace unstable SNAPSHOT dependency with stable coordinate where safe.'))
  if category=='kotlin':
   for p,t in files.items():
    if p.endswith('.kt') and '!!' in t: changes.append(ProposedChange(p,t,t.replace('!!','?'), 'Reduce a nullable assertion; requires review because semantics may change.'))
  return changes
 def apply(self,files,changes):
  out=dict(files)
  for c in changes: out[c.path]=c.new
  return out
