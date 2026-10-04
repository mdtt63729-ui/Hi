class ResultIntegrity:
 def build_status(self,run):
  return {'status':run.get('status'),'conclusion':run.get('conclusion'),'source':'github_api'}
 def artifact(self,artifact):
  return {'id':artifact.get('id'),'name':artifact.get('name'),'size':artifact.get('size_in_bytes'),'expired':artifact.get('expired'),'source':'github_api'}
