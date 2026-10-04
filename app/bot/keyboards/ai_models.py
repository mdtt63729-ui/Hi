from aiogram.utils.keyboard import InlineKeyboardBuilder
from app.ai.model_catalog import HEAD_MODELS, OPENROUTER_FIX_MODELS, NVIDIA_MODELS, MODEL_OPTIONS, model_key

ALL_SELECTABLE_MODELS=[model_key(p,m) for p,m in MODEL_OPTIONS]

def _add(b,models,current,prefix):
    for i,model in enumerate(models):
        idx=ALL_SELECTABLE_MODELS.index(model_key(prefix,model))
        label=('✓ ' if current==model else '')+model
        # Use a numeric callback to stay safely below Telegram's 64-byte callback_data limit.
        b.button(text=label[:60],callback_data=f'aimodel:set:{idx}')

def ai_model_kb(current='auto'):
    b=InlineKeyboardBuilder()
    b.button(text=('✅ Auto (Recommended)' if current=='auto' else '⚡ Auto (Recommended)'),callback_data='aimodel:auto')
    b.button(text='— Gemini / Head AI —',callback_data='aimodel:noop:gemini')
    _add(b,HEAD_MODELS,current,"gemini")
    b.button(text='— OpenRouter Specialists —',callback_data='aimodel:noop:openrouter')
    _add(b,OPENROUTER_FIX_MODELS,current,"openrouter")
    b.button(text='— NVIDIA NIM Specialists —',callback_data='aimodel:noop:nvidia')
    _add(b,NVIDIA_MODELS,current,"nvidia")
    b.button(text='⬅️ Back',callback_data='home'); b.adjust(1)
    return b.as_markup()
