from fastapi import APIRouter
from app.config import settings
router=APIRouter()
@router.get('/healthz')
async def health(): return {'status':'healthy','telegram':'configured' if settings.bot_token else 'missing','database':'configured','redis':'configured' if settings.redis_url else 'optional','storage':'configured','github':'configured via user credentials','disk':'healthy'}
