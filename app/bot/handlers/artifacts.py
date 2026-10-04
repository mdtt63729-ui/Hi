from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, BufferedInputFile
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from app.services.artifact_store import get
from app.utils.security import decrypt
from app.database.repository import get_connection, list_repos
from app.config import settings
from app.github.client import GitHubClient

router=Router()


def _download_keyboard(owner, repo, artifact_id, user_id):
    from app.services.artifact_delivery import artifact_keyboard
    return artifact_keyboard(owner, repo, artifact_id, user_id)


@router.message(Command('artifacts'))
async def artifacts_cmd(m:Message):
    parts=(m.text or '').split()
    if len(parts)>=2 and '/' in parts[1]:
        owner,repo=parts[1].split('/',1)
        run_id=int(parts[2]) if len(parts)>=3 and parts[2].isdigit() else None
        return await _show_repo_artifacts(m,owner,repo,run_id)
    await _show_repo_picker(m)


@router.callback_query(F.data=='artifacts')
async def artifacts_menu(c:CallbackQuery):
    await c.answer()
    await _show_repo_picker(c.message, edit=True)


async def _show_repo_picker(m, edit=False):
    repos=await list_repos(m.from_user.id)
    b=InlineKeyboardBuilder()
    for r in repos[:50]:
        b.button(text=f'📦 {r.owner}/{r.name}',callback_data=f'artifact:repo:{r.id}')
    b.button(text='⬅️ Main Menu',callback_data='home'); b.adjust(1)
    text='📦 Artifacts\n\nSelect a repository to see its recent workflow runs and artifacts.'
    if edit:
        await m.edit_text(text,reply_markup=b.as_markup())
    else:
        await m.answer(text,reply_markup=b.as_markup())


@router.callback_query(F.data.startswith('artifact:repo:'))
async def artifact_repo(c:CallbackQuery):
    await c.answer()
    rid=int(c.data.rsplit(':',1)[1])
    repo=next((r for r in await list_repos(c.from_user.id) if r.id==rid),None)
    if not repo: return await c.message.edit_text('❌ Repository not found.',reply_markup=None)
    conn=await get_connection(c.from_user.id)
    if not conn: return await c.message.edit_text('🔐 Connect GitHub first.')
    gh=GitHubClient(decrypt(conn.encrypted_pat,settings.encryption_key))
    try:
        runs=(await gh.runs(repo.owner,repo.name)).get('workflow_runs',[])
        b=InlineKeyboardBuilder()
        for run in runs[:15]:
            label=f'▶️ #{run.get("run_number") or run.get("id")} — {run.get("name") or "Workflow"}'
            b.button(text=label[:60],callback_data=f'artifact:run:{rid}:{run["id"]}')
        b.button(text='⬅️ Repositories',callback_data='artifacts'); b.adjust(1)
        await c.message.edit_text(f'📦 Artifacts — {repo.owner}/{repo.name}\n\nSelect a workflow run:',reply_markup=b.as_markup())
    finally: await gh.close()


@router.callback_query(F.data.startswith('artifact:run:'))
async def artifact_run(c:CallbackQuery):
    await c.answer('Loading artifacts…')
    _,_,rid,run_id=c.data.split(':')
    repo=next((r for r in await list_repos(c.from_user.id) if r.id==int(rid)),None)
    if not repo: return await c.message.edit_text('❌ Repository not found.')
    conn=await get_connection(c.from_user.id)
    if not conn: return await c.message.edit_text('🔐 Connect GitHub first.')
    gh=GitHubClient(decrypt(conn.encrypted_pat,settings.encryption_key))
    try:
        data=await gh.run_artifacts(repo.owner,repo.name,int(run_id))
        items=[a for a in data.get('artifacts',[]) if not a.get('expired')]
        if not items:
            return await c.message.edit_text('📦 No non-expired artifacts found for this workflow run.')
        lines=[f'📦 Artifacts — {repo.owner}/{repo.name}',f'Run: #{run_id}','']
        b=InlineKeyboardBuilder()
        for a in items[:20]:
            name=a.get('name') or f'artifact-{a["id"]}'
            size=int(a.get('size_in_bytes') or 0)
            lines.append(f'• {name} — {size:,} bytes')
            # Reuse the reliable short callback registry.
            from app.services.artifact_store import put
            from app.services.artifact_delivery import _token
            signed=_token(repo.owner,repo.name,a['id'],c.from_user.id)
            key=put(repo.owner,repo.name,a['id'],c.from_user.id,signed)
            b.button(text=f'📥 {name}'[:60],callback_data=f'artifact:download:{key}')
        b.button(text='⬅️ Runs',callback_data=f'artifact:repo:{repo.id}'); b.adjust(1)
        await c.message.edit_text('\n'.join(lines),reply_markup=b.as_markup())
    finally: await gh.close()


@router.callback_query(F.data.startswith('artifact:download:'))
async def artifact_download(c:CallbackQuery):
    await c.answer('Preparing artifact…')
    key=c.data.split(':',2)[2]
    item=get(key)
    if not item:
        return await c.message.answer('❌ This artifact download session expired. Open Artifacts again.')
    _,owner,repo,artifact_id,user_id,_token_value=item
    if int(user_id)!=int(c.from_user.id):
        return await c.answer('This download belongs to another user.',show_alert=True)
    conn=await get_connection(c.from_user.id)
    if not conn: return await c.message.answer('🔐 Connect GitHub first.')
    gh=GitHubClient(decrypt(conn.encrypted_pat,settings.encryption_key))
    try:
        meta=await gh.artifact_meta(owner,repo,artifact_id)
        if meta.get('expired'):
            return await c.message.answer('❌ This GitHub artifact has expired. Re-run the workflow to create a fresh artifact.')
        size=int(meta.get('size_in_bytes') or 0)
        if size>49*1024*1024:
            base=(settings.webhook_base_url or '').rstrip('/')
            if base and _token_value:
                from aiogram.utils.keyboard import InlineKeyboardBuilder
                b=InlineKeyboardBuilder(); b.button(text='📥 Download Artifact',url=f'{base}/download/{_token_value}')
                return await c.message.answer(f'📦 Artifact is {size:,} bytes and is too large for direct Telegram upload.',reply_markup=b.as_markup())
            return await c.message.answer('📦 Artifact is larger than Telegram direct-upload limit. Configure WEBHOOK_BASE_URL for a secure download link.')
        response=await gh.artifact_response(owner,repo,artifact_id)
        payload=response.content
        if not payload.startswith(b'PK'):
            raise RuntimeError('GitHub returned an unexpected artifact payload.')
        await c.message.answer_document(BufferedInputFile(payload,filename=f"{meta.get('name') or 'artifact'}.zip"),caption='📦 Artifact download ready.')
    except Exception as exc:
        await c.message.answer(f'❌ Artifact download failed.\n\n{str(exc)[:500]}')
    finally: await gh.close()


async def _show_repo_artifacts(m,owner,repo,run_id=None):
    conn=await get_connection(m.from_user.id)
    if not conn: return await m.answer('🔐 Connect GitHub first.')
    gh=GitHubClient(decrypt(conn.encrypted_pat,settings.encryption_key))
    try:
        if run_id is None:
            runs=(await gh.runs(owner,repo)).get('workflow_runs',[])
            if not runs: return await m.answer('⚙️ No workflow runs found.')
            run_id=runs[0]['id']
        data=await gh.run_artifacts(owner,repo,run_id)
        items=[a for a in data.get('artifacts',[]) if not a.get('expired')]
        if not items: return await m.answer(f'📦 No non-expired artifacts for run #{run_id}.')
        b=InlineKeyboardBuilder(); lines=[f'📦 Artifacts — {owner}/{repo}',f'Run: #{run_id}','']
        from app.services.artifact_store import put
        from app.services.artifact_delivery import _token
        for a in items[:20]:
            name=a.get('name') or f'artifact-{a["id"]}'; size=int(a.get('size_in_bytes') or 0)
            lines.append(f'• {name} — {size:,} bytes')
            key=put(owner,repo,a['id'],m.from_user.id,_token(owner,repo,a['id'],m.from_user.id))
            b.button(text=f'📥 {name}'[:60],callback_data=f'artifact:download:{key}')
        b.adjust(1); await m.answer('\n'.join(lines),reply_markup=b.as_markup())
    finally: await gh.close()
