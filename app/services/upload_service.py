from app.services.zip_service import ZipService
from app.services.project_detection_service import ProjectDetectionService
from app.services.comparison_service import ComparisonService
from app.services.update_service import UpdateService
class UploadService:
 def __init__(self,github=None):
  self.zip=ZipService(); self.detect=ProjectDetectionService(); self.compare=ComparisonService(github) if github else None; self.update=UpdateService(github) if github else None
 async def inspect(self,path):
  root=self.zip.extract(path); return {'root':str(root),'project':self.detect.detect(root)}
 async def sync(self,path,owner,repo,branch,mode='update',message='chore: sync project'):
  root=self.zip.extract(path); files=self.zip.read_files(root)
  diff=await self.compare.compare(owner,repo,branch,files)
  if mode=='update': selected=diff.added+diff.modified
  else: selected=diff.added+diff.modified
  result=await self.update.apply(owner,repo,branch,root,selected,message,delete=(mode=='sync'))
  return {'diff':diff.__dict__,'commit':result}
