import asyncio
class QueueService:
    def __init__(self): self.q=asyncio.Queue()
    async def put(self,item): await self.q.put(item)
    async def get(self): return await self.q.get()
