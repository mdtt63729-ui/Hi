from sqlalchemy import select
from .database import Session
from .models import AIUserPreference

async def get_ai_preference(telegram_user_id: int) -> tuple[str,str|None]:
    async with Session() as s:
        x=await s.scalar(select(AIUserPreference).where(AIUserPreference.telegram_user_id==telegram_user_id))
        if not x: return 'auto', None
        return x.mode, x.model

async def set_ai_preference(telegram_user_id: int, mode: str, model: str|None=None):
    async with Session() as s:
        x=await s.scalar(select(AIUserPreference).where(AIUserPreference.telegram_user_id==telegram_user_id))
        if not x:
            x=AIUserPreference(telegram_user_id=telegram_user_id,mode=mode,model=model); s.add(x)
        else:
            x.mode=mode; x.model=model
        await s.commit()
