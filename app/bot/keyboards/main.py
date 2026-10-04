from aiogram.utils.keyboard import InlineKeyboardBuilder
def main_kb():
 b=InlineKeyboardBuilder()
 for t,c in [('📦 Repositories','repos'),('📤 Upload Project','upload'),('🔄 Update Project','update'),('⚙️ Workflows','workflows'),('▶️ Run Workflow','run'),('📊 Build Status','runs'),('📜 Build Logs','logs'),('📥 Artifacts','artifacts'),('🔐 GitHub Connection','github'),('🔑 PAT Capabilities','pat:capabilities'),('⚙️ Settings','settings'),('❓ Help','help'),('🤖 AI Assistant','ai'),('🧠 AI Models','ai_models')]: b.button(text=t,callback_data=c)
 b.adjust(2); return b.as_markup()
def back_kb():
 b=InlineKeyboardBuilder(); b.button(text='⬅️ Back',callback_data='home'); b.button(text='🏠 Main Menu',callback_data='home'); return b.as_markup()
def confirm_kb(ok='confirm',cancel='home'):
 b=InlineKeyboardBuilder(); b.button(text='✅ Confirm',callback_data=ok); b.button(text='❌ Cancel',callback_data=cancel); return b.as_markup()
