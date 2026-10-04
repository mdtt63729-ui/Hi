from dataclasses import dataclass,field
from .permissions import PermissionPolicy
from .audit import AuditLog
from .knowledge import RepoKnowledge
from .dependency import DependencyIntelligence
from .testing import TestAgent
from .review import CodeReviewer
from .fix_engine import CodeFixEngine
from .rollback import RollbackManager

@dataclass
class AgentContext:
 user_request:str
 repository:str
 branch:str='main'
 approved:bool=False
 max_attempts:int=3
 files:dict[str,str]=field(default_factory=dict)

class AutonomousEngineer:
 def __init__(self,policy=None):
  self.policy=policy or PermissionPolicy(); self.audit=AuditLog(); self.knowledge={}; self.deps=DependencyIntelligence(); self.tests=TestAgent(); self.reviewer=CodeReviewer(); self.fixer=CodeFixEngine(); self.rollback=RollbackManager()
 def index(self,repo,files,metadata=None):
  k=RepoKnowledge(repo,metadata=metadata or {}); k.index(files); self.knowledge[repo]=k; return k
 def diagnose(self,repo,error,files=None):
  files=files if files is not None else self.knowledge.get(repo,RepoKnowledge(repo)).files
  text=error.lower(); cats=['kotlin','java','gradle','android_sdk','dependency','xml','resources','manifest','github_actions','yaml','signing','permissions','environment','configuration']
  category='configuration'
  for c in cats:
   if c.replace('_',' ') in text or c in text: category=c; break
  locations=self.knowledge.get(repo,RepoKnowledge(repo)).search(error)
  return {'category':category,'error':error,'locations':locations,'recommendations':['Inspect the failing boundary and rerun the smallest verification first.']}
 def run_maintenance(self,ctx):
  k=self.index(ctx.repository,ctx.files)
  return {'knowledge':k.metadata,'dependencies':[x.__dict__ for x in self.deps.scan(ctx.files)],'tests':[x.__dict__ for x in self.tests.inspect(ctx.files)],'review':[x.__dict__ for x in self.reviewer.review(ctx.files)]}
 def fix_and_verify(self,ctx,error,category=None):
  decision=self.policy.decide('code.modify',confirmed=ctx.approved)
  if not decision.allowed or decision.requires_confirmation:
   return {'status':'awaiting_approval','reason':decision.reason}
  diag=self.diagnose(ctx.repository,error,ctx.files); category=category or diag['category']; attempts=[]; current=dict(ctx.files)
  for attempt in range(1,max(1,min(ctx.max_attempts,3))+1):
   changes=self.fixer.propose(category,error,current)
   if not changes: attempts.append({'attempt':attempt,'status':'no_safe_automatic_fix'}); break
   current=self.fixer.apply(current,changes); attempts.append({'attempt':attempt,'changes':[c.__dict__ for c in changes],'status':'verification_required'})
   if self._static_verify(current): return {'status':'fixed_pending_build','attempts':attempts,'files':current,'diagnosis':diag}
  return {'status':'failed_to_fix','attempts':attempts,'diagnosis':diag}
 def _static_verify(self,files):
  for p,t in files.items():
   if t.count('{')!=t.count('}') and p.endswith(('.kt','.java','.py','.js','.ts')): return False
  return True
