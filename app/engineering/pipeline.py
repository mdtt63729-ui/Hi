from dataclasses import dataclass,field
from .agent import AutonomousEngineer,AgentContext
from .permissions import PermissionPolicy

@dataclass
class EngineeringPipeline:
 agent:AutonomousEngineer
 max_attempts:int=3
 async def handle_failure(self,ctx,error,run_build):
  history=[]
  for attempt in range(1,self.max_attempts+1):
   diagnosis=self.agent.diagnose(ctx.repository,error,ctx.files)
   history.append({'attempt':attempt,'phase':'diagnose','diagnosis':diagnosis})
   result=self.agent.fix_and_verify(ctx,error,diagnosis['category'])
   history.append({'attempt':attempt,'phase':'fix','result':result})
   if result.get('status')=='awaiting_approval': return {'status':'awaiting_approval','history':history}
   if result.get('status')!='fixed_pending_build': return {'status':'failed','history':history}
   ctx.files=result['files']
   build=await run_build(ctx.files,attempt)
   history.append({'attempt':attempt,'phase':'build','result':build})
   if build.get('success'): return {'status':'success','history':history}
   error=build.get('error','Build failed')
  return {'status':'exhausted','history':history}
