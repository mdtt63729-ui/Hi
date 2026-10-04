from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from app.database.repository import get_connection, list_repos, save_repo
from app.utils.security import decrypt
from app.config import settings
from app.github.client import GitHubClient
from app.bot.keyboards.main import back_kb, main_kb
from aiogram.utils.keyboard import InlineKeyboardBuilder
import asyncio

router = Router()


def _message(ev):
    return ev if isinstance(ev, Message) else ev.message


def repo_actions(repo_id: int, owner: str, name: str):
    b = InlineKeyboardBuilder()
    b.button(text=f'📁 Open {name}', callback_data=f'repo:open:{repo_id}')
    b.button(text='🗑️ Delete Repository', callback_data=f'repo:delete:{repo_id}')
    b.button(text='🧹 Empty + Delete History', callback_data=f'repo:wipe:{repo_id}')
    b.button(text='⬅️ Back', callback_data='repos')
    b.adjust(1)
    return b.as_markup()


async def _get_repo_for_user(user_id: int, repo_id: int):
    for r in await list_repos(user_id):
        if r.id == repo_id:
            return r
    return None


@router.message(Command('repo'))
async def repo(m: Message):
    parts = (m.text or '').split(maxsplit=1)
    if len(parts) != 2 or '/' not in parts[1]:
        return await m.answer('Usage: /repo owner/name')
    c = await get_connection(m.from_user.id)
    if not c:
        return await m.answer('🔐 Connect GitHub first.')
    owner, name = parts[1].split('/', 1)
    gh = GitHubClient(decrypt(c.encrypted_pat, settings.encryption_key))
    try:
        r = await gh.repo(owner, name)
        w = await gh.workflows(owner, name)
        saved = await save_repo(m.from_user.id, r)
        await m.answer(
            f'📁 {r["full_name"]}\n🌿 Branch: {r.get("default_branch")}\n'
            f'🔒 {r.get("visibility")}\n⚙️ Workflows: {w.get("total_count", 0)}',
            reply_markup=repo_actions(saved.id, owner, name),
        )
    finally:
        await gh.close()


@router.message(Command('workflows'))
async def workflows(m: Message):
    parts = (m.text or '').split(maxsplit=1)
    if len(parts) != 2 or '/' not in parts[1]:
        return await m.answer('Usage: /workflows owner/name')
    c = await get_connection(m.from_user.id)
    if not c:
        return await m.answer('🔐 Connect GitHub first.')
    owner, name = parts[1].split('/', 1)
    gh = GitHubClient(decrypt(c.encrypted_pat, settings.encryption_key))
    try:
        w = await gh.workflows(owner, name)
        lines = ['⚙️ Workflows'] + [f'• {x["name"]} — {x["id"]}' for x in w.get('workflows', [])]
        await m.answer('\n'.join(lines) or 'No workflows found.', reply_markup=back_kb())
    finally:
        await gh.close()


@router.message(Command('run'))
async def run(m: Message):
    await m.answer('▶️ Use the Run Workflow button to select a repository and workflow.')


@router.callback_query(F.data == 'repos')
async def repos(c: CallbackQuery):
    conn = await get_connection(c.from_user.id)
    if not conn:
        await c.message.edit_text('🔐 Connect GitHub first.', reply_markup=back_kb())
        return await c.answer()
    gh = GitHubClient(decrypt(conn.encrypted_pat, settings.encryption_key))
    try:
        remote = await gh.repos()
        for r in remote:
            await save_repo(c.from_user.id, r)
        local = await list_repos(c.from_user.id)
        b = InlineKeyboardBuilder()
        for r in local[:50]:
            b.button(text=f'📦 {r.name}', callback_data=f'repo:open:{r.id}')
        b.button(text='➕ New Repository', callback_data='repo:new')
        b.button(text='⬅️ Main Menu', callback_data='home')
        b.adjust(1)
        await c.message.edit_text('📦 Repositories\n\nSelect a repository:', reply_markup=b.as_markup())
    finally:
        await gh.close()
    await c.answer()


@router.callback_query(F.data.startswith('repo:open:'))
async def repo_open(c: CallbackQuery):
    rid = int(c.data.rsplit(':', 1)[1])
    r = await _get_repo_for_user(c.from_user.id, rid)
    if not r:
        await c.answer('Repository not found.', show_alert=True); return
    await c.message.edit_text(
        f'📁 {r.owner}/{r.name}\n🌿 {r.default_branch}\n🔒 {r.visibility or "unknown"}',
        reply_markup=repo_actions(r.id, r.owner, r.name),
    )
    await c.answer()


@router.callback_query(F.data.startswith('repo:delete:'))
async def repo_delete_confirm(c: CallbackQuery):
    rid = int(c.data.rsplit(':', 1)[1])
    r = await _get_repo_for_user(c.from_user.id, rid)
    if not r:
        await c.answer('Repository not found.', show_alert=True); return
    b = InlineKeyboardBuilder()
    b.button(text='⚠️ YES, DELETE REPOSITORY', callback_data=f'repo:delete_confirm:{rid}')
    b.button(text='Cancel', callback_data=f'repo:open:{rid}')
    b.adjust(1)
    await c.message.edit_text(
        f'⚠️ Permanent repository deletion\n\n'
        f'Repository: {r.owner}/{r.name}\n\n'
        'This deletes the GitHub repository and its project, branches, issues, releases and Actions history.\n'
        'This action cannot be undone from Gitofy.', reply_markup=b.as_markup())
    await c.answer()


@router.callback_query(F.data.startswith('repo:delete_confirm:'))
async def repo_delete(c: CallbackQuery):
    rid = int(c.data.rsplit(':', 1)[1])
    r = await _get_repo_for_user(c.from_user.id, rid)
    if not r:
        await c.answer('Repository not found.', show_alert=True); return
    await c.message.edit_text('⏳ Deleting repository…\n▰▱▱▱▱▱▱▱▱▱ 10%')
    conn = await get_connection(c.from_user.id)
    if not conn: return await c.message.edit_text('🔐 GitHub connection required.')
    gh = GitHubClient(decrypt(conn.encrypted_pat, settings.encryption_key))
    try:
        await gh.delete_repo(r.owner, r.name)
        from app.database.repository import forget_repo
        await forget_repo(c.from_user.id, rid)
        await c.message.edit_text('✅ Repository deleted successfully.\n\nThe GitHub repository is gone.', reply_markup=main_kb())
    except Exception:
        await c.message.edit_text('❌ Repository deletion failed.\n\nCheck that your PAT has repository deletion permission.')
    finally:
        await gh.close()
    await c.answer()


@router.callback_query(F.data.startswith('repo:wipe:'))
async def repo_wipe_confirm(c: CallbackQuery):
    rid = int(c.data.rsplit(':', 1)[1])
    r = await _get_repo_for_user(c.from_user.id, rid)
    if not r:
        await c.answer('Repository not found.', show_alert=True); return
    b = InlineKeyboardBuilder()
    b.button(text='⚠️ YES, EMPTY + RESET HISTORY', callback_data=f'repo:wipe_confirm:{rid}')
    b.button(text='Cancel', callback_data=f'repo:open:{rid}')
    b.adjust(1)
    await c.message.edit_text(
        f'🚨 EMPTY PROJECT + RESET HISTORY\n\nRepository: {r.owner}/{r.name}\n\n'
        'Gitofy will delete the GitHub repository and immediately recreate an empty repository with the same name/privacy.\n'
        'This removes the reachable Git history and Actions history from the recreated repository.\n\n'
        '⚠️ This is destructive. Continue?', reply_markup=b.as_markup())
    await c.answer()


@router.callback_query(F.data.startswith('repo:wipe_confirm:'))
async def repo_wipe(c: CallbackQuery):
    rid = int(c.data.rsplit(':', 1)[1])
    r = await _get_repo_for_user(c.from_user.id, rid)
    if not r:
        await c.answer('Repository not found.', show_alert=True); return
    conn = await get_connection(c.from_user.id)
    if not conn: return await c.message.edit_text('🔐 GitHub connection required.')
    token = decrypt(conn.encrypted_pat, settings.encryption_key)
    gh = GitHubClient(token)
    try:
        await c.message.edit_text('🧹 Emptying project + resetting history…\n▰▱▱▱▱▱▱▱▱▱ 10%')
        remote = await gh.repo(r.owner, r.name)
        private = bool(remote.get('private', True)); description = remote.get('description') or ''
        await gh.delete_repo(r.owner, r.name)
        await asyncio.sleep(2)
        new = None
        last = None
        for _ in range(6):
            try:
                new = await gh.create_repo(r.name, description=description, private=private, auto_init=False)
                break
            except Exception as exc:
                last = exc
                await asyncio.sleep(2)
        if new is None:
            raise last or RuntimeError('Repository recreation failed')
        await save_repo(c.from_user.id, new)
        await c.message.edit_text(
            '✅ Repository completely reset.\n\n'
            f'📦 {r.owner}/{r.name}\n'
            '🧹 Project files: Empty\n'
            '🕘 Git history: Reset\n'
            '⚙️ Actions history: Reset\n\n'
            'The repository is ready for a fresh project upload.', reply_markup=main_kb())
    except Exception:
        await c.message.edit_text(
            '❌ Complete reset failed.\n\n'
            'The operation may have stopped after deletion. Check GitHub before retrying.\n'
            'Required PAT permission: repository administration/deletion.')
    finally:
        await gh.close()
    await c.answer()
