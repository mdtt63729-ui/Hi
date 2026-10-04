from app.config import settings
from app.storage.local import LocalStorage
class StorageService:
    def __init__(self): self.local=LocalStorage(settings.storage_path)
    def path(self,kind,key): return self.local.path(kind,key)
