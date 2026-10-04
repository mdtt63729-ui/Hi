from sqlalchemy import select, delete
from .database import Session
from .models import User,GitHubConnection,Repository,RepositorySettings
from app.utils.security import encrypt,decrypt
from app.config import settings
async def get_user(tg,username=None):
    async with Session() as s:
        u=await s.scalar(select(User).where(User.telegram_id==tg))
        if not u: u=User(telegram_id=tg,username=username); s.add(u); await s.commit(); await s.refresh(u)
        return u
async def save_connection(tg,token,info,perms):
    async with Session() as s:
        old=await s.scalar(select(GitHubConnection).where(GitHubConnection.telegram_user_id==tg))
        if not old: old=GitHubConnection(telegram_user_id=tg,encrypted_pat=encrypt(token,settings.encryption_key)); s.add(old)
        else: old.encrypted_pat=encrypt(token,settings.encryption_key)
        old.github_user_id=info.get('id'); old.github_username=info.get('login'); old.permissions=perms; old.status='active'; await s.commit()
async def get_connection(tg):
    async with Session() as s: return await s.scalar(select(GitHubConnection).where(GitHubConnection.telegram_user_id==tg,GitHubConnection.status=='active'))
async def disconnect(tg):
    async with Session() as s:
        c=await s.scalar(select(GitHubConnection).where(GitHubConnection.telegram_user_id==tg));
        if c: c.status='disconnected'; c.encrypted_pat=''; await s.commit()
async def save_repo(tg,r):
    async with Session() as s:
        x=await s.scalar(select(Repository).where(Repository.telegram_user_id==tg,Repository.github_repo_id==r['id']))
        if not x: x=Repository(telegram_user_id=tg,github_repo_id=r['id'],owner=r['owner']['login'],name=r['name']); s.add(x)
        x.default_branch=r.get('default_branch') or 'main'; x.visibility=r.get('visibility'); await s.commit(); await s.refresh(x); return x
async def list_repos(tg):
    async with Session() as s: return (await s.scalars(select(Repository).where(Repository.telegram_user_id==tg).order_by(Repository.name))).all()

async def forget_repo(tg, repo_id):
    async with Session() as s:
        x = await s.scalar(select(Repository).where(Repository.telegram_user_id == tg, Repository.id == repo_id))
        if x:
            await s.delete(x)
            await s.commit()
