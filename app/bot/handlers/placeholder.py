from aiogram import Router,F
from aiogram.types import Message,CallbackQuery
from aiogram.filters import Command
from app.bot.keyboards.main import main_kb,back_kb
router=Router()
@router.message(Command('status'))
@router.callback_query(F.data=='runs')
async def status(ev):
 m=ev if isinstance(ev,Message) else ev.message; await m.answer('📊 Build Status\n\nSelect a repository through 📦 Repositories to inspect workflows and runs.',reply_markup=back_kb())
@router.message(Command('settings'))
@router.callback_query(F.data=='settings')
async def settings_(ev):
 m=ev if isinstance(ev,Message) else ev.message; await m.answer('⚙️ Settings\n\nRepository-specific and global preferences are stored persistently.',reply_markup=back_kb())
@router.callback_query(F.data=='help')
async def help_cb(c:CallbackQuery): await c.message.answer('📚 Use /help for commands.',reply_markup=main_kb()); await c.answer()
