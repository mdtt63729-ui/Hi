from enum import Enum
from dataclasses import dataclass

class Risk(str, Enum): SAFE='safe'; MODERATE='moderate'; DANGEROUS='dangerous'

RISK_MAP={
 'repo.read':Risk.SAFE,'file.read':Risk.SAFE,'logs.read':Risk.SAFE,'workflow.list':Risk.SAFE,
 'branch.create':Risk.MODERATE,'commit.create':Risk.MODERATE,'workflow.run':Risk.MODERATE,'issue.create':Risk.MODERATE,'pr.create':Risk.MODERATE,
 'repo.delete':Risk.DANGEROUS,'branch.delete':Risk.DANGEROUS,'file.delete':Risk.DANGEROUS,'sync.destructive':Risk.DANGEROUS,'force.operation':Risk.DANGEROUS,
 'code.modify':Risk.MODERATE,'release.publish':Risk.MODERATE,'pr.merge':Risk.DANGEROUS,'workflow.delete':Risk.DANGEROUS,
}

@dataclass(frozen=True)
class Decision:
 allowed: bool
 requires_confirmation: bool
 reason: str

class PermissionPolicy:
 def __init__(self, overrides=None, require_confirm_moderate=False):
  self.overrides=overrides or {}; self.require_confirm_moderate=require_confirm_moderate
 def decide(self, operation, confirmed=False):
  risk=RISK_MAP.get(operation,Risk.MODERATE)
  allowed=self.overrides.get(operation,True)
  if not allowed: return Decision(False,False,'Operation disabled by policy.')
  if risk is Risk.DANGEROUS and not confirmed: return Decision(True,True,'Dangerous operation requires explicit confirmation.')
  if risk is Risk.MODERATE and self.require_confirm_moderate and not confirmed: return Decision(True,True,'Moderate operation requires confirmation under policy.')
  return Decision(True,False,'Allowed by policy.')
