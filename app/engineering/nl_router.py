import re
from dataclasses import dataclass
@dataclass
class Intent:
 name:str; args:dict; risk:str='moderate'
class NaturalLanguageRouter:
 def parse(self,text):
  t=text.lower().strip()
  if 'review' in t and ('pr' in t or 'pull request' in t): return Intent('pr.review',{},'safe')
  if ('fix' in t or 'solve' in t) and 'issue' in t: return Intent('issue.fix',self._number(t,'issue'),'moderate')
  if 'rollback' in t: return Intent('rollback',{},'dangerous')
  if 'release' in t and any(x in t for x in ('create','publish')): return Intent('release.create',{},'moderate')
  if 'dependency' in t and any(x in t for x in ('check','scan','update')): return Intent('dependency.scan',{},'safe')
  if 'test' in t and any(x in t for x in ('run','generate','check')): return Intent('test.agent',{},'safe')
  if 'workflow' in t and any(x in t for x in ('run','start')): return Intent('workflow.run',{},'moderate')
  if 'build' in t and any(x in t for x in ('fix','error','failed')): return Intent('build.fix',{},'moderate')
  if 'build' in t: return Intent('workflow.run',{},'moderate')
  if 'issue' in t: return Intent('issue.list',{},'safe')
  if 'pr' in t or 'pull request' in t: return Intent('pr.list',{},'safe')
  return Intent('chat',{},'safe')
 def _number(self,t,key):
  m=re.search(rf'{key}\s*#?(\d+)',t); return {'number':int(m.group(1))} if m else {}
