from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from app.bot.states.states import GitofyStates
from app.bot.keyboards.settings import settings_kb, provider_key_kb
from app.bot.keyboards.main import main_kb
from app.database.ai_credentials import set_provider_key, clear_provider_key, provider_status
from app.database.repository import get_connection
from app.config import settings

router=Router()

PROVIDERS={
    'gemini': ('Gemini', 'GEMINI_API_KEY'),
    'openrouter': ('OpenRouter', 'OPENROUTER_API_KEY'),
    'nvidia': ('NVIDIA NIM', 'NVIDIA_API_KEY'),
}

def _allowed(user_id:int)->bool:
    admins=settings.admin_id_set
    return not admins or user_id in admins

async def _render(m:Message):
    conn=await get_connection(m.from_user.id)
    if not conn:
        text=('⚙️ Settings\n\n🤖 AI Providers\n\n'
              '🔒 Connect GitHub first. AI provider configuration is unlocked after GitHub connection.')
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        b=InlineKeyboardBuilder(); b.button(text='🔐 Connect GitHub',callback_data='github'); b.button(text='🏠 Main Menu',callback_data='home'); b.adjust(1)
        try: await m.edit_text(text,reply_markup=b.as_markup())
        except Exception: await m.answer(text,reply_markup=b.as_markup())
        return
    st=await provider_status()
    text=("⚙️ Settings\n\n"
          "🤖 AI Providers\n\n"
          f"Gemini API: {'🟢 Configured' if st['gemini'] else '🔴 Not configured'}\n"
          f"OpenRouter API: {'🟢 Configured' if st['openrouter'] else '🔴 Not configured'}\n"
          f"NVIDIA NIM API: {'🟢 Configured' if st['nvidia'] else '🔴 Not configured'}\n\n"
          "Choose a provider to add or replace its API key. Keys are stored encrypted and are never displayed.")
    try:
        await m.edit_text(text,reply_markup=settings_kb(st))
    except Exception:
        await m.answer(text,reply_markup=settings_kb(st))

@router.message(Command('settings'))
@router.callback_query(F.data=='settings')
async def settings_open(ev):
    m=ev if isinstance(ev,Message) else ev.message
    if isinstance(ev,CallbackQuery): await ev.answer()
    await _render(m)

@router.callback_query(F.data=='settings:ai_providers')
async def providers_open(c:CallbackQuery):
    await c.answer()
    await _render(c.message)

@router.callback_query(F.data.startswith('provider:set:'))
async def provider_set(c:CallbackQuery,state:FSMContext):
    provider=c.data.split(':')[-1]
    if provider not in PROVIDERS:
        await c.answer('Unknown provider',show_alert=True); return
    if not _allowed(c.from_user.id):
        await c.answer('You are not allowed to change provider keys.',show_alert=True); return
    await state.set_state(GitofyStates.waiting_ai_key)
    await state.update_data(ai_provider=provider)
    name,env=PROVIDERS[provider]
    await c.answer()
    await c.message.edit_text(
        f'🔐 Configure {name} API\n\n'
        f'Send your {env} in the next message.\n\n'
        'The key will be encrypted and stored. It will not be echoed back in the chat.\n'
        'Send /cancel to abort.',
        reply_markup=provider_key_kb(provider))

@router.message(GitofyStates.waiting_ai_key)
async def provider_key_received(m:Message,state:FSMContext):
    key=(m.text or '').strip()
    if key=='/cancel':
        await state.clear(); await _render(m); return
    data=await state.get_data(); provider=data.get('ai_provider')
    if provider not in PROVIDERS or not key:
        await m.answer('❌ Invalid API key. Please try again or send /cancel.')
        return
    # Delete the secret message immediately where Telegram permits it.
    try: await m.delete()
    except Exception: pass
    name,_=PROVIDERS[provider]
    status=await m.answer(f'🔄 Saving {name} API key securely…')
    try:
        await set_provider_key(provider,key)
        await state.clear()
        st=await provider_status()
        await status.edit_text(
            f'✅ {name} API configured successfully.\n\n'
            f'Gemini: {"🟢" if st["gemini"] else "🔴"}\n'
            f'OpenRouter: {"🟢" if st["openrouter"] else "🔴"}\n'
            f'NVIDIA NIM: {"🟢" if st["nvidia"] else "🔴"}\n\n'
            'The key is stored encrypted.\n'
            'Use AI Models to choose Auto or a specific fixer.',
            reply_markup=settings_kb(st))
    except Exception:
        await status.edit_text('❌ Could not save the API key. Check ENCRYPTION_KEY and database configuration.')

@router.callback_query(F.data.startswith('provider:clear:'))
async def provider_clear(c:CallbackQuery):
    provider=c.data.split(':')[-1]
    if provider not in PROVIDERS:
        await c.answer('Unknown provider',show_alert=True); return
    if not _allowed(c.from_user.id):
        await c.answer('Not allowed.',show_alert=True); return
    await clear_provider_key(provider)
    await c.answer('API key removed')
    await _render(c.message)
