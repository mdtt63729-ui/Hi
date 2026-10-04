from dataclasses import dataclass
import re
@dataclass
class ReviewFinding:
 severity:str; path:str; line:int; message:str; recommendation:str
class CodeReviewer:
 def review(self, files):
  out=[]
  for p,t in files.items():
   for i,line in enumerate(t.splitlines(),1):
    if re.search(r'\b(password|token|api[_-]?key|secret)\s*=\s*["\']',line,re.I): out.append(ReviewFinding('critical',p,i,'Possible hard-coded secret.','Move secret to environment/secret storage.'))
    if 'TODO' in line and 'security' in line.lower(): out.append(ReviewFinding('medium',p,i,'Security TODO remains in code.','Resolve before release.'))
    if 'shell=True' in line: out.append(ReviewFinding('high',p,i,'Shell execution may enable command injection.','Use argument arrays and validate inputs.'))
  return out
