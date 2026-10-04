from app.utils.security import sign_value
from app.config import settings
class ArtifactService:
    def tier(self,size): return 1 if (size or 0)<=50*1024*1024 else 2 if (size or 0)<=2*1024*1024*1024 else 3
    def sign(self,artifact_id): return sign_value(str(artifact_id),settings.artifact_signing_secret,900) if settings.artifact_signing_secret else None
