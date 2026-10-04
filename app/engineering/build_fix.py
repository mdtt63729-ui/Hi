from dataclasses import dataclass
@dataclass
class FixAttempt:
 number:int; error:str; diagnosis:dict; fix:dict; build:dict
class BuildFixLoop:
 def __init__(self,agent,max_attempts=3): self.agent=agent; self.max_attempts=max(1,min(max_attempts,3))
 async def run(self,ctx,build_fn,error):
  attempts=[]
  for n in range(1,self.max_attempts+1):
   d=self.agent.diagnose(ctx.repository,error,ctx.files); f=self.agent.fix_and_verify(ctx,error,d['category'])
   if f.get('status')=='awaiting_approval': return {'status':'awaiting_approval','attempts':attempts,'next':f}
   if f.get('status')!='fixed_pending_build': return {'status':'failed_to_fix','attempts':attempts,'next':f}
   ctx.files=f['files']; b=await build_fn(ctx.files,n); attempts.append(FixAttempt(n,error,d,f,b).__dict__)
   if b.get('success'): return {'status':'success','attempts':attempts,'files':ctx.files}
   error=b.get('error','Build failed')
  return {'status':'max_attempts_reached','attempts':attempts}
