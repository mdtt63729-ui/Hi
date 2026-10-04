import io,zipfile,re
class LogService:
 def __init__(self,github=None): self.github=github
 async def workflow_logs(self,owner,repo,run_id):
  r=await self.github.logs(owner,repo,run_id); return r.content
 def extract_errors(self,text):
  lines=text.splitlines(); keys=('error','failed','failure','exception','caused by','e:')
  return '\n'.join(line for line in lines if any(k in line.lower() for k in keys))
 def error_txt(self,text): return self.extract_errors(text).encode()
