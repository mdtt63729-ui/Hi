import asyncio
class LockService:
    def __init__(self): self.locks={}
    async def acquire(self,key):
        lock=self.locks.setdefault(key,asyncio.Lock()); await lock.acquire(); return lock
