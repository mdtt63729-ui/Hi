from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from app.bot.states.states import GitofyStates
from app.config import settings
from app.services.zip_service import ZipService
from app.services.project_detection_service import detect_project
from app.utils.file_stats import zip_stats, fmt_bytes
from app.services.upload_progress import ProgressReporter
from app.github.client import GitHubClient
from app.database.repository import get_connection, list_repos
from app.utils.security import decrypt
from pathlib import Path
from zipfile import ZipFile
import base64, uuid, asyncio

router = Router()

def repo_picker(user_repos, action):
    b = InlineKeyboardBuilder()
    for r in user_repos[:50]:
        b.button(text=f'📦 {r.owner}/{r.name}', callback_data=f'project:{action}:{r.id}')
    b.button(text='❌ Cancel', callback_data='home')
    b.adjust(1)
    return b.as_markup()

@router.message(Command('upload'))
async def upload_start(m: Message, state: FSMContext):
    await state.set_state(GitofyStates.waiting_zip)
    await state.update_data(project_action='upload')
    await m.answer('📤 Send your ZIP project now. Gitofy will validate it and then let you choose the GitHub repository.')

@router.callback_query(F.data == 'upload')
async def upload_button(c: CallbackQuery, state: FSMContext):
    await c.answer()
    await state.set_state(GitofyStates.waiting_zip)
    await state.update_data(project_action='upload')
    await c.message.edit_text('📤 Send your ZIP project now. Gitofy will validate it and then let you choose the GitHub repository.')

@router.callback_query(F.data == 'update')
async def update_button(c: CallbackQuery, state: FSMContext):
    await c.answer()
    await state.set_state(GitofyStates.waiting_zip)
    await state.update_data(project_action='update')
    await c.message.edit_text('🔄 Send the new ZIP project now. The selected repository will be replaced by the new project while Git history is preserved.')

class CountingWriter:
    def __init__(self, path, reporter):
        self.fp = open(path, 'wb'); self.reporter = reporter; self.done = 0
        self.loop = asyncio.get_running_loop(); self.pending = None
    def write(self, data):
        n = self.fp.write(data); self.done += n
        if self.pending is None or self.pending.done():
            self.pending = self.loop.create_task(self.reporter.update(self.done))
        return n
    def flush(self): return self.fp.flush()
    def close(self): return self.fp.close()
    def seek(self, *a): return self.fp.seek(*a)
    def tell(self): return self.fp.tell()

@router.message(GitofyStates.waiting_zip, F.document)
async def upload_zip(m: Message, state: FSMContext):
    if not m.document or not (m.document.file_name or '').lower().endswith('.zip'):
        return await m.answer('❌ Please send a .zip document.')
    data = await state.get_data(); action = data.get('project_action', 'upload')
    op = uuid.uuid4().hex
    dest = Path(settings.storage_path) / 'uploads' / str(m.from_user.id) / op
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / (m.document.file_name or 'project.zip')
    original_size = int(getattr(m.document, 'file_size', 0) or 0)
    status = await m.answer(f'⏳ Uploading…\n\nOriginal ZIP size: {fmt_bytes(original_size)} ({original_size:,} bytes)\n\n[{ProgressReporter.bar(0)}] 0%')
    reporter = ProgressReporter(status, 'Uploading', original_size or 1); writer = CountingWriter(path, reporter)
    try:
        f = await m.bot.get_file(m.document.file_id)
        await m.bot.download_file(f.file_path, destination=writer, chunk_size=8 * 1024 * 1024)
        writer.flush(); writer.close()
        stats = zip_stats(path); root = Path(dest) / 'project'; ZipService().extract(path, root); info = detect_project(root)
        await state.update_data(zip_path=str(path), zip_root=str(root), project_action=action)
        await reporter.finish(
            f'🔎 Project analyzed\n\n📦 ZIP size: {fmt_bytes(stats["size_bytes"])} ({stats["size_bytes"]:,} bytes)\n'
            f'📄 Files: {stats["file_count"]:,}\n💾 Expanded: {fmt_bytes(stats["expanded_bytes"])}\n\n'
            f'Android: {"🟢" if info["android"] else "⚪"}\nGradle: {"🟢" if info["gradle"] else "⚪"}\n'
            f'Kotlin: {"🟢" if info["kotlin"] else "⚪"}\nJava: {"🟢" if info["java"] else "⚪"}\n\n'
            f'Next: select the repository to {"replace" if action == "update" else "upload"} the project.'
        )
        repos = await list_repos(m.from_user.id)
        if not repos:
            return await m.answer('❌ No saved repositories found. Connect GitHub and open Repositories first.')
        await state.set_state(GitofyStates.waiting_repo)
        await m.answer('📦 Select GitHub repository\n\n' + ('The new project will replace the existing working tree.' if action == 'update' else 'Empty repositories are supported; Gitofy will create the first commit and branch automatically.'), reply_markup=repo_picker(repos, action))
    except Exception as e:
        try: writer.close()
        except Exception: pass
        await state.clear(); await reporter.finish(f'❌ ZIP upload/validation failed.\n\n{str(e)[:800]}')


async def _upload_empty_repo_via_api(gh, owner, name, branch, root, progress=None, message='chore(gitofy): upload project from ZIP [skip ci]'):
    """Create the first commit directly through GitHub's Git Data API.

    Empty GitHub repositories have no refs, so operations that require an
    existing branch (clone, contents/ref lookup, PATCH ref, etc.) can return
    HTTP 409. For the initial upload we create blobs -> a root tree -> a
    commit with no parents -> a brand-new refs/heads/<branch> ref.
    """
    root = Path(root)
    files = [p for p in root.rglob('*') if p.is_file() and '.git' not in p.parts]
    entries = []
    total = len(files) or 1
    for i, path in enumerate(files, 1):
        rel = path.relative_to(root).as_posix()
        raw = path.read_bytes()
        blob = await gh.create_blob(owner, name, base64.b64encode(raw).decode('ascii'))
        entries.append({'path': rel, 'mode': '100644', 'type': 'blob', 'sha': blob['sha']})
        if progress:
            progress(5 + (i / total) * 70)
    tree = await gh.create_tree(owner, name, None, entries)
    if progress:
        progress(78)
    commit = await gh.create_commit(owner, name, message, tree['sha'], [])
    if progress:
        progress(90)
    await gh.create_ref(owner, name, branch, commit['sha'])
    if progress:
        progress(99)
    return {'sha': commit['sha'], 'files': len(files), 'bytes': sum(p.stat().st_size for p in files), 'deleted': 0}

async def _run_git_sync(c: CallbackQuery, state: FSMContext, repo, action: str):
    data = await state.get_data(); zip_path = data.get('zip_path')
    if not zip_path or not Path(zip_path).is_file():
        await state.clear(); return await c.message.edit_text('❌ Uploaded ZIP session expired. Please upload the project again.')
    conn = await get_connection(c.from_user.id)
    if not conn: return await c.message.edit_text('🔐 Connect GitHub first.')
    gh = GitHubClient(decrypt(conn.encrypted_pat, settings.encryption_key))
    try:
        remote = await gh.repo(repo.owner, repo.name)
        branch = remote.get('default_branch') or 'main'
        empty = bool(remote.get('size', 0) == 0 and not remote.get('default_branch'))
        if action == 'update' and empty: action = 'upload'
        title = 'Uploading' if action == 'upload' else 'Replacing'
        progress_message = await c.message.edit_text(f'🚀 {title} project…\n\n📦 {repo.owner}/{repo.name}\n🌿 {branch}\n🗂️ Repository: {"EMPTY — creating first commit" if empty else "existing project"}\n\n[{ProgressReporter.bar(0)}] 0%')
        loop = asyncio.get_running_loop(); last = {'p': -1}
        async def edit(p):
            p = int(max(0, min(99, round(p))))
            if p == last['p']: return
            last['p'] = p
            try: await progress_message.edit_text(f'🚀 {title} project…\n\n📦 {repo.owner}/{repo.name}\n🌿 {branch}\n🗂️ Repository: {"EMPTY — creating first commit" if empty else "existing project"}\n\n[{ProgressReporter.bar(p)}] {p}%')
            except Exception: pass
        def progress(p): asyncio.run_coroutine_threadsafe(edit(p), loop)
        # A truly empty GitHub repository has no branch/ref. Do NOT route
        # its first upload through any operation that expects an existing ref;
        # GitHub may answer HTTP 409 (Git Repository is empty). Build the
        # initial commit explicitly via Git Data API instead.
        if empty:
            result = await _upload_empty_repo_via_api(
                gh, repo.owner, repo.name, branch, data.get('zip_root'), progress,
                'chore(gitofy): initial project upload from ZIP [skip ci]'
            )
        else:
            from app.services.git_cli_engine import GitCliEngine
            engine = GitCliEngine(decrypt(conn.encrypted_pat, settings.encryption_key))
            if action == 'upload':
                result = await asyncio.to_thread(engine.sync_zip, repo.owner, repo.name, branch, zip_path, progress, 'chore(gitofy): upload project from ZIP [skip ci]')
            else:
                result = await asyncio.to_thread(engine.update_zip, repo.owner, repo.name, branch, zip_path, progress, 'chore(gitofy): replace project from ZIP [skip ci]')
        await edit(100); await asyncio.sleep(.15)
        await progress_message.edit_text(f'✅ Project {"uploaded" if action == "upload" else "replaced"} successfully.\n\n📦 {repo.owner}/{repo.name}\n🌿 {branch}\n📄 Files uploaded: {result.get("files", 0)}\n🧹 Old files removed: {result.get("deleted", 0)}\n📝 Commit: {str(result.get("sha", ""))[:12]}')
        await state.clear()
    except Exception as exc:
        await c.message.edit_text(f'❌ Project upload failed.\n\n{str(exc)[:1200]}')
    finally: await gh.close()

@router.callback_query(GitofyStates.waiting_repo, F.data.startswith('project:'))
async def choose_project_repo(c: CallbackQuery, state: FSMContext):
    await c.answer('Starting project upload…')
    parts = c.data.split(':')
    if len(parts) != 3: return await c.message.edit_text('❌ Invalid repository selection.')
    action = parts[1]
    try: rid = int(parts[2])
    except ValueError: return await c.message.edit_text('❌ Invalid repository selection.')
    repos = await list_repos(c.from_user.id); repo = next((r for r in repos if r.id == rid), None)
    if not repo: return await c.message.edit_text('❌ Repository not found.')
    await _run_git_sync(c, state, repo, action)
