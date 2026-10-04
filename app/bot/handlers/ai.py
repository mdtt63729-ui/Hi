import asyncio
from aiogram import Router,F
from aiogram.types import Message,CallbackQuery
from aiogram.filters import Command
from aiogram.enums import ChatAction
from app.ai.manager import AIProviderManager
from app.ai.intent import IntentEngine
from app.config import settings
from app.ai.model_catalog import HEAD_MODELS, FIX_MODELS, provider_for, split_model_key
from app.bot.keyboards.ai_models import ALL_SELECTABLE_MODELS
from app.database.ai_preferences import get_ai_preference, set_ai_preference
from app.bot.keyboards.ai_models import ai_model_kb
from app.services.ai_progress import AIFixProgress
from app.bot.handlers.common import home_message_id, remember_home

router=Router(); mgr=AIProviderManager(settings)

@router.callback_query(F.data=='ai')
async def ai_open(c:CallbackQuery):
    await c.message.answer('🤖 Gitofy AI Assistant\n\nTell me what you want to do with GitHub, builds, workflows, logs or project deployment.')
    await c.answer()

@router.message(Command('ai_models'))
async def ai_models_cmd(m:Message):
    mode,model=await get_ai_preference(m.from_user.id)
    current='auto' if mode=='auto' else (model or 'auto')
    await m.answer('🤖 AI Fixer Model\n\nAuto is the default. In Auto mode, Gemini Head AI selects the best fixer for each failure.\n\nSelect a model:',reply_markup=ai_model_kb(current))

@router.callback_query(F.data=='ai_models')
async def ai_models_cb(c:CallbackQuery):
    mode,model=await get_ai_preference(c.from_user.id)
    current='auto' if mode=='auto' else (model or 'auto')
    await c.message.edit_text('🤖 AI Fixer Model\n\nAuto is the default. Gemini Head AI will choose the best specialist for each build failure.\n\nSelect a model:',reply_markup=ai_model_kb(current))
    await c.answer()

@router.callback_query(F.data=='aimodel:auto')
async def ai_auto(c:CallbackQuery):
    await set_ai_preference(c.from_user.id,'auto',None)
    await c.message.edit_text('🤖 AI Fixer Model\n\n✅ Auto (Recommended)\n\nGemini Head AI will automatically select the best available fixer for each problem.',reply_markup=ai_model_kb('auto'))
    await c.answer('Auto mode enabled')

@router.callback_query(F.data.startswith('aimodel:noop:'))
async def ai_noop(c:CallbackQuery):
    await c.answer('Provider heading', show_alert=False)

@router.callback_query(F.data.startswith('aimodel:set:'))
async def ai_set(c:CallbackQuery):
    try:
        idx=int(c.data.split(':',2)[2]); model_key_value=ALL_SELECTABLE_MODELS[idx]; provider, model=split_model_key(model_key_value)
    except (ValueError,IndexError):
        return await c.answer('Unknown model',show_alert=True)
    await set_ai_preference(c.from_user.id,'manual',model_key_value)
    await c.message.edit_text(f'🤖 AI Fixer Model\n\n✅ Selected:\n{provider} / {model}\n\nFailed workflows will use this model as the fixer. Gemini remains the Head AI for analysis.',reply_markup=ai_model_kb(model))
    await c.answer('Model selected')

async def _typing_answer(m:Message,text:str):
    for _ in range(max(1,min(8,(len(text)//280)+1))):
        await m.bot.send_chat_action(m.chat.id,ChatAction.TYPING)
        await asyncio.sleep(0.55)
    mid=home_message_id(m.chat.id,m.from_user.id)
    if mid:
        try:
            await m.bot.edit_message_text(text[:4090],chat_id=m.chat.id,message_id=mid,reply_markup=__import__('app.bot.keyboards.main',fromlist=['main_kb']).main_kb())
            return
        except Exception:
            pass
    sent=await m.answer(text[:4090]); remember_home(sent)

@router.message(F.text & ~F.text.startswith('/'))
async def ai_text(m:Message):
    if len(m.text)>2000: return
    try:
        intent=await IntentEngine().detect(mgr,m.text)
        action=intent.get('action')
        if action and action!='unknown':
            model_key,answer=await mgr.ask(f'User request: {m.text}\nDetected action: {action}',preferred='auto')
            _, display_model=split_model_key(model_key)
            await _typing_answer(m,f'🤖 Head AI: {display_model}\n\n{answer}')
    except Exception:
        return


async def _download_document(m:Message, file_id:str):
    f=await m.bot.get_file(file_id)
    import io
    buf=io.BytesIO()
    await m.bot.download_file(f.file_path,destination=buf)
    return buf.getvalue()

async def _media_team_answer(m:Message,name:str,data:bytes,mime:str):
    mode,selected=await get_ai_preference(m.from_user.id)
    manager=AIProviderManager(settings)
    head=manager.head_model
    # Media is first understood by the Gemini Head AI. If the user manually selected
    # a capable specialist, it is then given the same evidence as a second team member.
    parts=[__import__('app.ai.media',fromlist=['make_part']).make_part(name,data,mime)]
    progress=await m.answer(f'🤖 Head AI: {head}\n🔎 Analyzing attachment…\n\n{AIFixProgress.bar(8)} 8%\nReading {name}…')
    try:
        await m.bot.send_chat_action(m.chat.id,ChatAction.TYPING)
        head_answer=await manager.ask_multimodal(head,'Analyze this attachment carefully. Extract every useful fact, error, instruction, visual detail, code issue, and actionable requirement. This analysis will be handed to another AI fixer.',parts,system='You are Gitofy Head AI. Be precise. Do not invent unseen content.')
        await progress.edit_text(f'🤖 Head AI: {head}\n🔎 Analysis complete\n\n{AIFixProgress.bar(55)} 55%\nSelecting the best team member…')
        if mode=='manual' and selected and manager.is_configured(selected): fixer=selected
        else: fixer,_=await manager.choose_fixer(head_answer)
        fixer_prompt=('HEAD AI ANALYSIS:\n'+head_answer[:50000]+'\n\nUSER ATTACHMENT: '+name+'\nUse the analysis above to answer the user or explain the concrete changes needed. If code/build repair is requested, return actionable file-level guidance.')
        await progress.edit_text(f'🤖 Head AI: {head}\n🔧 Fixing/Explaining with: {fixer}\n\n{AIFixProgress.bar(78)} 78%\nPassing Head AI findings to the specialist…')
        await m.bot.send_chat_action(m.chat.id,ChatAction.TYPING)
        answer=await manager.ask_model(fixer,fixer_prompt,system='You are Gitofy Specialist AI. Use the Head AI evidence, do not invent missing facts, and give a concise actionable result.')
        await progress.edit_text(f'🤖 Head AI: {head}\n🔧 Fixing/Explaining with: {fixer}\n\n{AIFixProgress.bar(100)} 100%\n✅ Team analysis completed\n\n{answer[:3300]}')
    except Exception as exc:
        await progress.edit_text(f'🤖 Head AI: {head}\n❌ Team analysis failed\n\n{str(exc)[:1200]}')

@router.message(F.photo)
async def ai_photo(m:Message):
    data=await _download_document(m,m.photo[-1].file_id)
    await _media_team_answer(m,'telegram-photo.jpg',data,'image/jpeg')

@router.message(F.video)
async def ai_video(m:Message):
    data=await _download_document(m,m.video.file_id)
    await _media_team_answer(m,m.video.file_name or 'telegram-video.mp4',data,m.video.mime_type or 'video/mp4')

@router.message(F.document)
async def ai_document(m:Message):
    # ZIP upload remains owned by the upload FSM handler; ordinary documents are AI inputs.
    data=await _download_document(m,m.document.file_id)
    await _media_team_answer(m,m.document.file_name or 'attachment',data,m.document.mime_type or 'application/octet-stream')
