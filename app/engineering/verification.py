from dataclasses import dataclass
import hashlib
@dataclass
class VerificationResult:
 files_ok:bool; structure_ok:bool; workflow_ok:bool; artifact_found:bool; passed:bool; details:list
class BuildVerifier:
 def verify(self,files,workflow=None,artifacts=None):
  details=[]; structure=any(x in files for x in ('settings.gradle','settings.gradle.kts')) and any(x.startswith('app/') for x in files)
  files_ok=all(isinstance(v,str) for v in files.values())
  workflow_ok=True
  if workflow is not None:
   from .workflow import WorkflowGenerator; workflow_ok=WorkflowGenerator().validate(workflow)['valid']
  artifact_found=bool(artifacts)
  passed=files_ok and structure and workflow_ok and artifact_found
  return VerificationResult(files_ok,structure,workflow_ok,artifact_found,passed,details)
 def fingerprint(self,files):
  h=hashlib.sha256()
  for p in sorted(files): h.update(p.encode()); h.update(files[p].encode())
  return h.hexdigest()
