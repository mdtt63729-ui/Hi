from aiogram import Router,F
from aiogram.types import Message,CallbackQuery
from aiogram.filters import Command
from app.bot.keyboards.main import main_kb
from app.bot.messages.texts import WELCOME
router=Router()
_HOME={}

def remember_home(message): _HOME[(message.chat.id,message.from_user.id)] = message.message_id

def home_message_id(chat_id,user_id): return _HOME.get((chat_id,user_id))

@router.message(Command('start'))
async def start(m:Message):
    sent=await m.answer(WELCOME,reply_markup=main_kb(),parse_mode='Markdown')
    remember_home(sent)

@router.message(Command('help'))
async def help_(m:Message):
    text='📚 Gitofy Help\n\nUse the buttons below or commands such as /connect, /repos, /upload, /workflows, /runs, /logs, /artifacts, /settings, and PAT Capabilities from the main menu.'
    mid=home_message_id(m.chat.id,m.from_user.id)
    if mid:
        try:
            await m.bot.edit_message_text(text,chat_id=m.chat.id,message_id=mid,reply_markup=main_kb())
            return
        except Exception: pass
    sent=await m.answer(text,reply_markup=main_kb()); remember_home(sent)

@router.callback_query(F.data=='home')
async def home(c:CallbackQuery):
    await c.message.edit_text(WELCOME,reply_markup=main_kb(),parse_mode='Markdown')
    remember_home(c.message); await c.answer()
