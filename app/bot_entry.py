import asyncio
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from app.config import settings, validate_required_ai_apis
from app.database.database import init_db
from app.bot.handlers.common import router as common_router
from app.bot.handlers.github import router as github_router
from app.bot.handlers.repository import router as repository_router
from app.bot.handlers.placeholder import router as placeholder_router
from app.bot.handlers.upload import router as upload_router
from app.bot.handlers.ai import router as ai_router
from app.bot.handlers.pat import router as pat_router
from app.bot.handlers.artifacts import router as artifact_bot_router

def build_dispatcher():
    dp = Dispatcher(storage=MemoryStorage())
    for router in (common_router, github_router, repository_router, artifact_bot_router, placeholder_router, upload_router, ai_router, pat_router):
        dp.include_router(router)
    return dp

async def main():
    validate_required_ai_apis()
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is required to run the Telegram bot")
    await init_db()
    bot = Bot(settings.bot_token)
    try:
        await build_dispatcher().start_polling(bot)
    finally:
        await bot.session.close()
