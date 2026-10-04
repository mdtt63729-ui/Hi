from aiogram.utils.keyboard import InlineKeyboardBuilder

def settings_kb(status=None):
    status = status or {}
    b=InlineKeyboardBuilder()
    b.button(text=f"🤖 Gemini API {'🟢' if status.get('gemini') else '🔴'}", callback_data='provider:set:gemini')
    b.button(text=f"🌐 OpenRouter API {'🟢' if status.get('openrouter') else '🔴'}", callback_data='provider:set:openrouter')
    b.button(text=f"🟩 NVIDIA NIM API {'🟢' if status.get('nvidia') else '🔴'}", callback_data='provider:set:nvidia')
    b.button(text='🧠 AI Models', callback_data='ai_models')
    b.button(text='⚡ Auto Mode', callback_data='aimodel:auto')
    b.button(text='⬅️ Main Menu', callback_data='home')
    b.adjust(1)
    return b.as_markup()

def provider_key_kb(provider):
    b=InlineKeyboardBuilder()
    b.button(text='🗑️ Remove API Key', callback_data=f'provider:clear:{provider}')
    b.button(text='⬅️ AI Providers', callback_data='settings:ai_providers')
    b.button(text='🏠 Main Menu', callback_data='home')
    b.adjust(1)
    return b.as_markup()
