import httpx, logging
from app.utils.errors import OperationError
log=logging.getLogger(__name__)
class GitHubClient:
    def __init__(self,token): self.token=token; self.base='https://api.github.com'; self.client=httpx.AsyncClient(timeout=httpx.Timeout(30,connect=10),headers={'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28','Authorization':f'Bearer {token}'})
    async def close(self): await self.client.aclose()
    async def request(self,method,path,**kwargs):
        for attempt in range(3):
            try:
                r=await self.client.request(method,self.base+path,**kwargs)
                if r.status_code==429 or r.status_code>=500:
                    if attempt<2: import asyncio; await asyncio.sleep(2**attempt); continue
                if r.status_code>=400:
                    code={401:'unauthorized',403:'forbidden',404:'not_found',409:'conflict',422:'validation_error'}.get(r.status_code,'github_error')
                    raise OperationError(f'GitHub rejected the request ({r.status_code}).',code,False,r.status_code)
                return r
            except httpx.HTTPError:
                if attempt==2: raise OperationError('GitHub network request failed.','network_error',True)
        raise OperationError('GitHub request failed.','github_error')
    async def json(self,method,path,**kwargs): return (await self.request(method,path,**kwargs)).json()
    async def user(self): return await self.json('GET','/user')
    async def rate_limit(self): return await self.json('GET','/rate_limit')
    async def repos(self,page=1,per_page=30): return await self.json('GET','/user/repos',params={'page':page,'per_page':per_page,'sort':'updated'})
    async def repo(self,owner,name): return await self.json('GET',f'/repos/{owner}/{name}')
    async def create_repo(self,name,description='',private=True,auto_init=False): return await self.json('POST','/user/repos',json={'name':name,'description':description,'private':private,'auto_init':auto_init})
    async def delete_repo(self,owner,name): await self.request('DELETE',f'/repos/{owner}/{name}')
    async def branches(self,owner,name): return await self.json('GET',f'/repos/{owner}/{name}/branches',params={'per_page':100})
    async def workflows(self,owner,name): return await self.json('GET',f'/repos/{owner}/{name}/actions/workflows',params={'per_page':100})
    async def workflow_yaml(self,owner,name,path,ref): return await self.json('GET',f'/repos/{owner}/{name}/contents/{path}',params={'ref':ref})
    async def dispatch(self,owner,name,wf,ref,inputs=None): await self.request('POST',f'/repos/{owner}/{name}/actions/workflows/{wf}/dispatches',json={'ref':ref,'inputs':inputs or {}})
    async def runs(self,owner,name,page=1): return await self.json('GET',f'/repos/{owner}/{name}/actions/runs',params={'page':page,'per_page':20})
    async def run(self,owner,name,run_id): return await self.json('GET',f'/repos/{owner}/{name}/actions/runs/{run_id}')
    async def jobs(self,owner,name,run_id): return await self.json('GET',f'/repos/{owner}/{name}/actions/runs/{run_id}/jobs',params={'per_page':100})
    async def cancel(self,owner,name,run_id): await self.request('POST',f'/repos/{owner}/{name}/actions/runs/{run_id}/cancel')
    async def rerun(self,owner,name,run_id): await self.request('POST',f'/repos/{owner}/{name}/actions/runs/{run_id}/rerun')
    async def logs(self,owner,name,run_id): return await self.request('GET',f'/repos/{owner}/{name}/actions/runs/{run_id}/logs')
    async def artifacts(self,owner,name): return await self.json('GET',f'/repos/{owner}/{name}/actions/artifacts',params={'per_page':100})
    async def run_artifacts(self,owner,name,run_id): return await self.json('GET',f'/repos/{owner}/{name}/actions/runs/{run_id}/artifacts',params={'per_page':100})
    async def artifact_meta(self,owner,name,artifact_id): return await self.json('GET',f'/repos/{owner}/{name}/actions/artifacts/{artifact_id}')
    async def artifact_response(self,owner,name,artifact_id):
        return await self.request('GET',f'/repos/{owner}/{name}/actions/artifacts/{artifact_id}/zip',headers={'Accept':'application/vnd.github+json'},follow_redirects=True)
    async def tree(self,owner,name,sha): return await self.json('GET',f'/repos/{owner}/{name}/git/trees/{sha}',params={'recursive':'1'})
    async def ref(self,owner,name,branch): return await self.json('GET',f'/repos/{owner}/{name}/git/ref/heads/{branch}')
    async def commit(self,owner,name,sha): return await self.json('GET',f'/repos/{owner}/{name}/git/commits/{sha}')
    async def blob(self,owner,name,sha): return await self.json('GET',f'/repos/{owner}/{name}/git/blobs/{sha}')
    async def repository_files(self,owner,name,branch='main',max_files=400, max_bytes_per_file=100000):
        """Return a repository-wide text snapshot plus the complete tree manifest."""
        ref=await self.ref(owner,name,branch); tree=await self.tree(owner,name,ref['object']['sha'])
        entries=[x for x in tree.get('tree',[]) if x.get('type')=='blob']
        files={}
        for item in entries[:max_files]:
            path=item.get('path','')
            if any(part in path.split('/') for part in ('.git','build','.gradle','node_modules','__pycache__')): continue
            if (item.get('size') or 0)>max_bytes_per_file: continue
            try:
                data=await self.blob(owner,name,item['sha'])
                import base64
                raw=base64.b64decode(data.get('content',''), validate=False)
                files[path]=raw.decode('utf-8')
            except (UnicodeDecodeError, ValueError, KeyError):
                continue
        return {'manifest':[x.get('path') for x in entries], 'files':files, 'tree':tree}
    async def create_blob(self,owner,name,content): return await self.json('POST',f'/repos/{owner}/{name}/git/blobs',json={'content':content,'encoding':'base64'})
    async def create_tree(self,owner,name,base,entries):
        payload={'tree':entries}
        if base: payload['base_tree']=base
        return await self.json('POST',f'/repos/{owner}/{name}/git/trees',json=payload)
    async def create_ref(self,owner,name,branch,sha):
        return await self.json('POST',f'/repos/{owner}/{name}/git/refs',json={'ref':f'refs/heads/{branch}','sha':sha})
    async def create_commit(self,owner,name,message,tree,parents): return await self.json('POST',f'/repos/{owner}/{name}/git/commits',json={'message':message,'tree':tree,'parents':parents})
    async def update_ref(self,owner,name,branch,sha): return await self.json('PATCH',f'/repos/{owner}/{name}/git/refs/heads/{branch}',json={'sha':sha,'force':False})

# Broad GitHub PAT-backed API surface. Each method delegates permission checks
# to GitHub; Gitofy never attempts to manufacture or escalate token privileges.

def _add_pat_methods():
    async def orgs(self, page=1, per_page=100): return await self.json('GET','/user/orgs',params={'page':page,'per_page':per_page})
    async def org_repos(self, org, page=1): return await self.json('GET',f'/orgs/{org}/repos',params={'page':page,'per_page':100})
    async def org_members(self, org, page=1): return await self.json('GET',f'/orgs/{org}/members',params={'page':page,'per_page':100})
    async def org_teams(self, org): return await self.json('GET',f'/orgs/{org}/teams',params={'per_page':100})
    async def repo_collaborators(self, owner, name): return await self.json('GET',f'/repos/{owner}/{name}/collaborators',params={'per_page':100})
    async def repo_hooks(self, owner, name): return await self.json('GET',f'/repos/{owner}/{name}/hooks',params={'per_page':100})
    async def create_repo_hook(self, owner, name, config, events=None, active=True): return await self.json('POST',f'/repos/{owner}/{name}/hooks',json={'name':'web','active':active,'events':events or ['push'],'config':config})
    async def delete_repo_hook(self, owner, name, hook_id): await self.request('DELETE',f'/repos/{owner}/{name}/hooks/{hook_id}')
    async def deploy_keys(self, owner, name): return await self.json('GET',f'/repos/{owner}/{name}/keys',params={'per_page':100})
    async def deployments(self, owner, name, page=1): return await self.json('GET',f'/repos/{owner}/{name}/deployments',params={'page':page,'per_page':100})
    async def deployment_statuses(self, owner, name, deployment_id): return await self.json('GET',f'/repos/{owner}/{name}/deployments/{deployment_id}/statuses',params={'per_page':100})
    async def commit_statuses(self, owner, name, ref): return await self.json('GET',f'/repos/{owner}/{name}/commits/{ref}/status')
    async def check_runs(self, owner, name, ref): return await self.json('GET',f'/repos/{owner}/{name}/commits/{ref}/check-runs',params={'per_page':100})
    async def code_scanning_alerts(self, owner, name): return await self.json('GET',f'/repos/{owner}/{name}/code-scanning/alerts',params={'per_page':100})
    async def dependabot_alerts(self, owner, name): return await self.json('GET',f'/repos/{owner}/{name}/dependabot/alerts',params={'per_page':100})
    async def secret_scanning_alerts(self, owner, name): return await self.json('GET',f'/repos/{owner}/{name}/secret-scanning/alerts',params={'per_page':100})
    async def repo_secrets(self, owner, name): return await self.json('GET',f'/repos/{owner}/{name}/actions/secrets',params={'per_page':100})
    async def repo_variables(self, owner, name): return await self.json('GET',f'/repos/{owner}/{name}/actions/variables',params={'per_page':100})
    async def environments(self, owner, name): return await self.json('GET',f'/repos/{owner}/{name}/environments',params={'per_page':100})
    async def rulesets(self, owner, name): return await self.json('GET',f'/repos/{owner}/{name}/rulesets',params={'per_page':100})
    async def notifications(self, page=1): return await self.json('GET','/notifications',params={'page':page,'per_page':100})
    async def gists(self, page=1): return await self.json('GET','/gists',params={'page':page,'per_page':100})
    async def keys(self): return await self.json('GET','/user/keys',params={'per_page':100})
    async def gpg_keys(self): return await self.json('GET','/user/gpg_keys',params={'per_page':100})
    async def codespaces(self): return await self.json('GET','/user/codespaces',params={'per_page':100})
    async def org_runners(self, org): return await self.json('GET',f'/orgs/{org}/actions/runners',params={'per_page':100})
    async def repo_runners(self, owner, name): return await self.json('GET',f'/repos/{owner}/{name}/actions/runners',params={'per_page':100})
    async def packages(self, org=None, package_type=None, page=1):
        path=f'/orgs/{org}/packages' if org else '/user/packages'
        params={'page':page,'per_page':100}
        if package_type: params['package_type']=package_type
        return await self.json('GET',path,params=params)
    async def audit_log(self, org, page=1): return await self.json('GET',f'/orgs/{org}/audit-log',params={'page':page,'per_page':100})
    async def enterprise(self, slug): return await self.json('GET',f'/enterprises/{slug}')
    async def repo_discussions(self, owner, name, page=1): return await self.json('GET',f'/repos/{owner}/{name}/discussions',params={'page':page,'per_page':100})
    async def search_repos(self, q, page=1): return await self.json('GET','/search/repositories',params={'q':q,'page':page,'per_page':100})
    async def search_code(self, q, page=1): return await self.json('GET','/search/code',params={'q':q,'page':page,'per_page':100})
    async def user_followers(self, username=None): return await self.json('GET',f'/users/{username}/followers' if username else '/user/followers',params={'per_page':100})
    for name, fn in locals().copy().items():
        if callable(fn) and name not in {'self'} and name not in {'_add_pat_methods'}:
            setattr(GitHubClient, name, fn)

_add_pat_methods()

def _add_pat_action_methods():
    async def update_repo(self, owner, name, **fields): return await self.json('PATCH',f'/repos/{owner}/{name}',json=fields)
    async def star_repo(self, owner, name): await self.request('PUT',f'/user/starred/{owner}/{name}')
    async def unstar_repo(self, owner, name): await self.request('DELETE',f'/user/starred/{owner}/{name}')
    async def follow(self, username): await self.request('PUT',f'/user/following/{username}')
    async def unfollow(self, username): await self.request('DELETE',f'/user/following/{username}')
    async def mark_thread_read(self, thread_id): await self.request('PATCH',f'/notifications/threads/{thread_id}')
    async def repo_subscriptions(self, owner, name): return await self.json('GET',f'/repos/{owner}/{name}/subscription')
    async def create_gist(self, files, description='', public=False): return await self.json('POST','/gists',json={'description':description,'public':public,'files':files})
    async def delete_gist(self, gist_id): await self.request('DELETE',f'/gists/{gist_id}')
    async def org_hooks(self, org): return await self.json('GET',f'/orgs/{org}/hooks',params={'per_page':100})
    async def create_org_hook(self, org, config, events=None, active=True): return await self.json('POST',f'/orgs/{org}/hooks',json={'name':'web','active':active,'events':events or ['push'],'config':config})
    async def delete_org_hook(self, org, hook_id): await self.request('DELETE',f'/orgs/{org}/hooks/{hook_id}')
    async def org_actions_permissions(self, org): return await self.json('GET',f'/orgs/{org}/actions/permissions')
    async def repo_actions_permissions(self, owner, name): return await self.json('GET',f'/repos/{owner}/{name}/actions/permissions')
    async def codespace(self, name): return await self.json('GET',f'/user/codespaces/{name}')
    async def start_codespace(self, name): return await self.request('POST',f'/user/codespaces/{name}/start')
    async def stop_codespace(self, name): return await self.request('POST',f'/user/codespaces/{name}/stop')
    async def delete_codespace(self, name): await self.request('DELETE',f'/user/codespaces/{name}')
    async def package_versions(self, package_type, package_name, org=None, page=1):
        base=f'/orgs/{org}/packages/{package_type}/{package_name}/versions' if org else f'/user/packages/{package_type}/{package_name}/versions'
        return await self.json('GET',base,params={'page':page,'per_page':100})
    async def delete_package_version(self, package_type, package_name, version_id, org=None):
        base=f'/orgs/{org}/packages/{package_type}/{package_name}/versions/{version_id}' if org else f'/user/packages/{package_type}/{package_name}/versions/{version_id}'
        await self.request('DELETE',base)
    async def org_audit_log(self, org, phrase=None, page=1):
        params={'page':page,'per_page':100}
        if phrase: params['phrase']=phrase
        return await self.json('GET',f'/orgs/{org}/audit-log',params=params)
    for name, fn in locals().copy().items():
        if callable(fn) and name not in {'self','_add_pat_action_methods'}: setattr(GitHubClient,name,fn)

_add_pat_action_methods()
