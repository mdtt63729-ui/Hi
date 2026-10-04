from pathlib import Path
import base64
class UpdateService:
    async def apply(self,gh,owner,name,branch,root,diff,mode='update',message='Update project via Gitofy'):
        ref=await gh.ref(owner,name,branch); head=ref['object']['sha']; base=await gh.commit(owner,name,head); base_tree=base['tree']['sha']; entries=[]
        paths=set(diff['added'])|set(diff['modified'])
        for rel in paths:
            data=Path(root,rel).read_bytes(); content=base64.b64encode(data).decode()
            blob=await gh.json('POST',f'/repos/{owner}/{name}/git/blobs',json={'content':content,'encoding':'base64'})
            entries.append({'path':rel,'mode':'100644','type':'blob','sha':blob['sha']})
        if mode=='sync':
            for rel in diff['deleted']: entries.append({'path':rel,'mode':'100644','type':'blob','sha':None})
        if not entries: return None
        tree=await gh.create_tree(owner,name,base_tree,entries); commit=await gh.create_commit(owner,name,message,tree['sha'],[head]); await gh.update_ref(owner,name,branch,commit['sha']); return commit
