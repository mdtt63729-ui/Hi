import asyncio, logging
from fastapi import FastAPI
from aiogram import Bot,Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from app.config import settings
from app.database.database import init_db
from app.utils.logger import setup_logging
from app.api.health import router as health_router
from app.api.webhooks import router as webhook_router
from app.bot.handlers.common import router as common_router
from app.bot.handlers.github import router as github_router
from app.bot.handlers.placeholder import router as placeholder_router
from app.bot.handlers.upload import router as upload_router
from app.bot.handlers.ai import router as ai_router
from app.bot.handlers.repository import router as repository_router
from app.api.artifacts import router as artifact_router
from app.api.engineering import router as engineering_router
log=logging.getLogger(__name__)
app=FastAPI(title='Gitofy',version='1.1')
app.include_router(health_router); app.include_router(webhook_router); app.include_router(artifact_router); app.include_router(engineering_router)
async def bot_loop():
    bot=Bot(settings.bot_token); dp=Dispatcher(storage=MemoryStorage())
    for r in [common_router,github_router,repository_router,placeholder_router,upload_router,ai_router]: dp.include_router(r)
    await dp.start_polling(bot)
@app.on_event('startup')
async def startup():
    setup_logging(settings.log_level); await init_db()
    if not settings.bot_token: log.warning('BOT_TOKEN is not configured; API-only mode')
    else: app.state.bot_task=asyncio.create_task(bot_loop())
@app.on_event('shutdown')
async def shutdown():
    t=getattr(app.state,'bot_task',None)
    if t: t.cancel()
if __name__=='__main__':
    import uvicorn; uvicorn.run('app.main:app',host=settings.health_host,port=settings.health_port)
