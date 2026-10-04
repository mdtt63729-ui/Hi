import asyncio, io, zipfile
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from app.config import settings
from app.database.repository import get_connection
from app.utils.security import decrypt
from app.github.client import GitHubClient
from app.services.workflow_monitor import WorkflowMonitor
from app.services.workflow_renderer import render_workflow
from app.services.artifact_delivery import deliver_artifacts
from app.services.ai_progress import AIFixProgress
from app.ai.manager import AIProviderManager
from app.ai.orchestrator import AIFixOrchestrator
from app.services.git_cli_engine import GitCliEngine
from app.database.ai_preferences import get_ai_preference

router=Router()


def _gh(user_id):
    return get_connection(user_id)

async def _client(user_id):
    c=await get_connection(user_id)
    if not c: return None
    return GitHubClient(decrypt(c.encrypted_pat,settings.encryption_key))


def repo_keyboard(owner,name,action='wf'):
    b=InlineKeyboardBuilder(); b.button(text=f'📦 {owner}/{name}',callback_data=f'{action}:repo:{owner}:{name}'); return b.as_markup()

@router.message(Command('workflows'))
async def workflows_cmd(m:Message):
    parts=(m.text or '').split(maxsplit=1)
    if len(parts)!=2 or '/' not in parts[1]: return await m.answer('Usage: /workflows owner/name')
    owner,name=parts[1].split('/',1); gh=await _client(m.from_user.id)
    if not gh: return await m.answer('🔐 Connect GitHub first.')
    try:
        data=await gh.workflows(owner,name); ws=data.get('workflows',[])
        if not ws: return await m.answer('⚙️ No GitHub Actions workflows found.')
        b=InlineKeyboardBuilder()
        for w in ws[:30]: b.button(text=f'▶️ {w.get("name","Workflow")}',callback_data=f'wf:run:{owner}:{name}:{w["id"]}')
        b.button(text='⬅️ Main Menu',callback_data='home'); b.adjust(1)
        await m.answer('⚙️ Workflows\n\nSelect a workflow to run:',reply_markup=b.as_markup())
    finally: await gh.close()

@router.callback_query(F.data=='workflows')
async def workflows_cb(c:CallbackQuery):
    await c.answer(); await c.message.answer('Use /workflows owner/name to load the real GitHub Actions workflow list.')

@router.message(Command('run'))
async def run_cmd(m:Message):
    parts=(m.text or '').split()
    if len(parts)!=3 or '/' not in parts[1]: return await m.answer('Usage: /run owner/name workflow_id')
    owner,name=parts[1].split('/',1)
    await _start_run(m,owner,name,parts[2])

@router.callback_query(F.data.startswith('wf:run:'))
async def run_cb(c:CallbackQuery):
    await c.answer('Starting workflow…'); parts=c.data.split(':',4); _,_,owner,name,wid=parts
    await _start_run(c.message,owner,name,wid)

async def _start_run(m,owner,name,wid):
    gh=await _client(m.from_user.id)
    if not gh: return await m.answer('🔐 Connect GitHub first.')
    try:
        repo=await gh.repo(owner,name); branch=repo.get('default_branch') or 'main'

        # Snapshot the latest run BEFORE dispatch. Without this guard GitHub can
        # briefly return the previous run after a dispatch, causing Gitofy to
        # monitor the wrong run and show no live steps.
        before=(await gh.runs(owner,name)).get('workflow_runs',[])
        before_ids={int(r.get('id')) for r in before if r.get('id') is not None}
        before_latest=max(before_ids) if before_ids else 0

        await gh.dispatch(owner,name,wid,branch)
        status=await m.answer(
            f'▶️ Workflow dispatched\n\nRepository: {owner}/{name}\nWorkflow: {wid}\nBranch: {branch}\n\n⏳ Waiting for the new run…'
        )

        run=None
        for _ in range(45):
            runs=(await gh.runs(owner,name)).get('workflow_runs',[])
            candidates=[r for r in runs
                        if int(r.get('workflow_id') or 0)==int(wid)
                        and int(r.get('id') or 0)>before_latest]
            if candidates:
                candidates.sort(key=lambda r:int(r.get('id') or 0), reverse=True)
                run=candidates[0]
                break
            await asyncio.sleep(2)

        if not run:
            return await status.edit_text(
                '❌ Workflow was dispatched, but GitHub did not expose the new run yet.\n\n'
                'Use Workflows again after a few seconds to retry.'
            )

        # Show the first real run state immediately, including whatever jobs/steps
        # GitHub has exposed at that moment. The monitor will edit this exact message.
        jobs=(await gh.jobs(owner,name,run['id'])).get('jobs',[])
        first=render_workflow(run,jobs,title='Gitofy • Live Workflow')
        await status.edit_text(first)
        await _monitor_and_repair(m,gh,owner,name,branch,run,status)
    except Exception as e:
        await m.answer(f'❌ Workflow start failed: {str(e)[:700]}')
    finally: await gh.close()

async def _monitor_and_repair(m,gh,owner,name,branch,run,status):
    monitor=WorkflowMonitor()
    last_render = None
    edit_lock = asyncio.Lock()

    async def update(run,jobs):
        nonlocal last_render
        text = render_workflow(run,jobs,title='Gitofy • Live Workflow')
        if text == last_render:
            return
        async with edit_lock:
            # Re-check after waiting for an earlier edit to finish.
            if text == last_render:
                return
            try:
                await status.edit_text(text)
                last_render = text
            except Exception as exc:
                # Do not swallow the state silently. The next poll retries the
                # exact same state automatically.
                if 'message is not modified' in str(exc).lower():
                    last_render = text
                    return
                raise

    final,jobs=await monitor.monitor(gh,owner,name,run['id'],update=update,initial=2,maximum=2)
    final_text=render_workflow(final,jobs,title='Gitofy • Build Successful' if final.get('conclusion')=='success' else 'Gitofy • Build Failed')
    try:
        await status.edit_text(final_text)
    except Exception:
        pass
    if final.get('conclusion')=='success':
        await m.answer(f'✅ Build successful\n\nWorkflow: {final.get("name") or "GitHub Actions"}\nRun: #{final.get("run_number") or final.get("id")}')
        await deliver_artifacts(m,gh,owner,name,final['id'])
        return
    await m.answer(f'❌ Build failed\n\nWorkflow: {final.get("name") or "GitHub Actions"}\nRun: #{final.get("run_number") or final.get("id")}\n\n🤖 Starting AI build repair…')
    if not settings.ai_autofix_enabled:
        await m.answer('AI Auto-Fix is disabled (AI_AUTOFIX_ENABLED=false).')
        return
    await _ai_repair(m,gh,owner,name,branch,final)

async def _failed_log(gh,owner,name,run_id):
    response=await gh.logs(owner,name,run_id)
    raw=response.content
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            parts=[]
            for n in z.namelist():
                if n.endswith('/') or len(parts)>50: continue
                try: parts.append(z.read(n).decode('utf-8',errors='replace'))
                except Exception: pass
            return '\n\n'.join(parts)[-50000:]
    except zipfile.BadZipFile:
        return raw.decode('utf-8',errors='replace')[-50000:]

async def _ai_repair(m,gh,owner,name,branch,failed_run):
    progress_msg=await m.answer('🤖 Head AI: preparing…\n🔧 Fixing with: selecting specialist…\n\n░░░░░░░░░░░░░░░░░░░░░░░░ 0%\nCollecting failed workflow data…')
    progress=AIFixProgress(progress_msg); progress.head_model=AIProviderManager(settings).head_model
    manager=AIProviderManager(settings); orchestrator=AIFixOrchestrator(manager)
    mode,selected_model=await get_ai_preference(m.from_user.id)
    if mode != 'manual': selected_model='auto'
    progress.selected_model=selected_model
    engine=GitCliEngine(decrypt((await get_connection(m.from_user.id)).encrypted_pat,settings.encryption_key))
    error=await _failed_log(gh,owner,name,failed_run['id'])
    for attempt in range(1,4):
        try:
            await progress.update(5+(attempt-1)*29,f'Attempt {attempt}/3: reading latest failed workflow log…')
            snapshot=await gh.repository_files(owner,name,branch,max_files=settings.ai_max_repo_files,max_bytes_per_file=settings.ai_max_ai_file_bytes)
            files=snapshot['files']
            await progress.update(11+(attempt-1)*29,f'Attempt {attempt}/3: inspected {len(snapshot["manifest"]):,} repository files; {len(files):,} text files loaded.')
            base=8+(attempt-1)*29
            plan=await orchestrator.create_plan(error,files,progress=progress,progress_base=base,progress_span=25,selected_model=selected_model)
            await progress.update(30+(attempt-1)*29,f'AI diagnosis: {plan.explanation[:500]}',model=plan.model)
            if not plan.files:
                raise RuntimeError('The specialist AI could not produce a safe change to an existing repository file.')
            await progress.update(40+(attempt-1)*29,f'Applying {len(plan.files)} file change(s) locally…',model=plan.model)
            loop=asyncio.get_running_loop()
            def git_progress(pct):
                try:
                    asyncio.run_coroutine_threadsafe(progress.update(70+(attempt-1)*9+int(pct*0.10),f'Pushing fix to GitHub… {pct:.0f}%'),loop)
                except Exception:
                    pass
            result=await asyncio.to_thread(engine.apply_file_changes,owner,name,branch,plan.files,progress=git_progress)
            if not result.get('changed'):
                raise RuntimeError('AI produced no repository change.')
            progress.fixer_provider = manager.provider_name(plan.model)
            await progress.update(70+(attempt-1)*10,f'Push completed: {len(result["files"])} file(s) committed at {result["sha"][:12]}. Re-running workflow…',model=plan.model)
            await gh.rerun(owner,name,failed_run['id'])
            await progress.update(78+(attempt-1)*6,'Fix pushed successfully. Monitoring the new workflow run in real time…',model=plan.model)
            newrun=None
            for _ in range(30):
                runs=(await gh.runs(owner,name)).get('workflow_runs',[])
                newer=[r for r in runs if r.get('workflow_id')==failed_run.get('workflow_id') and r.get('id')!=failed_run.get('id')]
                if newer: newrun=newer[0]; break
                await asyncio.sleep(2)
            if not newrun:
                await progress.finish(False,'Fix was pushed, but GitHub did not expose the rerun yet.',files=len(result['files']),model=plan.model); return
            live=await m.answer(render_workflow(newrun,[],title='Gitofy • AI Repair Build'))
            live_last = {'text': None}
            async def update_live(r, j):
                text = render_workflow(r, j, title='Gitofy • AI Repair Build')
                if text == live_last['text']:
                    return
                try:
                    await live.edit_text(text)
                    live_last['text'] = text
                except Exception:
                    # Keep monitoring; the next poll automatically retries.
                    return
            final,jobs=await WorkflowMonitor().monitor(gh,owner,name,newrun['id'],update=update_live,initial=2,maximum=2)
            if final.get('conclusion')=='success':
                await progress.finish(True,f'Build passed after AI repair. Commit: {result["sha"][:12]}',files=len(result['files']),model=plan.model)
                await m.answer('✅ AI-repaired build succeeded.')
                await deliver_artifacts(m,gh,owner,name,final['id'])
                return
            error=await _failed_log(gh,owner,name,final['id'])
            failed_run=final
            await progress.update(min(95,82+attempt*5),f'Rerun failed. Latest logs collected; starting attempt {attempt+1}/3…',model=plan.model)
        except Exception as exc:
            if attempt>=3:
                await progress.finish(False,f'Automatic repair stopped after 3 attempts. {str(exc)[:700]}',files=0,model=getattr(progress,'model',None)); return
            await progress.update(min(95,25+attempt*20),f'Attempt {attempt} failed safely: {str(exc)[:350]}. Re-observing the latest workflow…',model=getattr(progress,'model',None))
    await progress.finish(False,'Maximum AI repair attempts reached.',files=0,model=getattr(progress,'model',None))
