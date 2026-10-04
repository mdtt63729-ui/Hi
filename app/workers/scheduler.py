import asyncio
from app.services.cleanup_service import CleanupService
from app.config import settings
async def cleanup_loop():
    while True:
        CleanupService().clean(settings.storage_path,settings.cleanup_minutes*60)
        await asyncio.sleep(3600)
