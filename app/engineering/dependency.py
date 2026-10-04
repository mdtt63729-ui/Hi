import re
from dataclasses import dataclass
@dataclass
class DependencyFinding:
 name:str; current:str; kind:str; severity:str; recommendation:str
class DependencyIntelligence:
 def scan(self, files):
  findings=[]
  for path,text in files.items():
   if path.endswith(('.gradle','.gradle.kts')):
    for m in re.finditer(r'([A-Za-z0-9_.-]+):([A-Za-z0-9_.-]+):([0-9][\w.-]*)',text):
     g=f'{m.group(1)}:{m.group(2)}'; v=m.group(3)
     if 'SNAPSHOT' in v.upper(): findings.append(DependencyFinding(g,v,'unstable','medium','Pin a stable release.'))
   if path.endswith('requirements.txt'):
    for line in text.splitlines():
     if line.startswith(('#','-')): continue
     m=re.match(r'([A-Za-z0-9_.-]+)(?:==|>=|~=)?\s*([\w.*+-]*)',line)
     if m and not m.group(2): findings.append(DependencyFinding(m.group(1),'unversioned','python','medium','Pin a compatible version.'))
  return findings
