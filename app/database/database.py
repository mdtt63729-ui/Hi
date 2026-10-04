from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.config import settings
class Base(DeclarativeBase): pass
engine=create_async_engine(settings.database_url, pool_pre_ping=True)
Session=async_sessionmaker(engine, expire_on_commit=False)
async def init_db():
    from . import models
    async with engine.begin() as c: await c.run_sync(Base.metadata.create_all)
