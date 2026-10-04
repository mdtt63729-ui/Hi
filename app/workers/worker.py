import asyncio
class Worker:
    def __init__(self,queue): self.queue=queue
    async def run(self):
        while True:
            job=await self.queue.get()
            try: await job()
            finally: self.queue.q.task_done()
