from app.engineering.workflow import WorkflowGenerator
class WorkflowService:
 def __init__(self,github=None): self.github=github; self.generator=WorkflowGenerator()
 def generate_android(self,release=True): return self.generator.android(release)
 def validate_yaml(self,text): return self.generator.validate(text)
 async def discover(self,owner,repo): return await self.github.workflows(owner,repo)
 async def dispatch(self,owner,repo,workflow,branch,inputs=None): return await self.github.dispatch(owner,repo,workflow,branch,inputs)
 async def cancel(self,owner,repo,run_id): return await self.github.cancel(owner,repo,run_id)
 async def rerun(self,owner,repo,run_id): return await self.github.rerun(owner,repo,run_id)
