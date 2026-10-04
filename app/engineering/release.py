from dataclasses import dataclass
@dataclass
class ReleasePlan:
 tag:str; title:str; body:str; artifacts:list
class ReleaseAutomation:
 def plan(self,tag,title,body,artifacts=None): return ReleasePlan(tag,title,body,artifacts or [])
