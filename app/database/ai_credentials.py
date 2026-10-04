from sqlalchemy import select
from .database import Session
from .models import AIProviderCredential
from app.config import settings
from app.utils.security import encrypt, decrypt

async def set_provider_key(provider: str, api_key: str):
    provider = provider.strip().lower()
    async with Session() as s:
        row = await s.scalar(select(AIProviderCredential).where(AIProviderCredential.provider == provider))
        if not row:
            row = AIProviderCredential(provider=provider, encrypted_api_key=encrypt(api_key, settings.encryption_key))
            s.add(row)
        else:
            row.encrypted_api_key = encrypt(api_key, settings.encryption_key)
        await s.commit()
    setattr(settings, f'{provider}_api_key', api_key)

async def clear_provider_key(provider: str):
    provider = provider.strip().lower()
    async with Session() as s:
        row = await s.scalar(select(AIProviderCredential).where(AIProviderCredential.provider == provider))
        if row:
            await s.delete(row)
            await s.commit()
    setattr(settings, f'{provider}_api_key', '')

async def load_provider_keys():
    async with Session() as s:
        rows = (await s.scalars(select(AIProviderCredential))).all()
    for row in rows:
        try:
            key = decrypt(row.encrypted_api_key, settings.encryption_key)
        except Exception:
            continue
        if row.provider in {'gemini','openrouter','nvidia'}:
            setattr(settings, f'{row.provider}_api_key', key)

async def provider_status():
    return {
        'gemini': bool(settings.gemini_api_key),
        'openrouter': bool(settings.openrouter_api_key),
        'nvidia': bool(settings.nvidia_api_key),
    }
