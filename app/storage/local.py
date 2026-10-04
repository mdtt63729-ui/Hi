from pathlib import Path
class LocalStorage:
    def __init__(self,root): self.root=Path(root); self.root.mkdir(parents=True,exist_ok=True)
    def path(self,kind,key): p=self.root/kind/key; p.parent.mkdir(parents=True,exist_ok=True); return p
    async def put_stream(self,kind,key,stream):
        p=self.path(kind,key)
        with open(p,'wb') as f:
            async for c in stream: f.write(c)
        return str(p)
