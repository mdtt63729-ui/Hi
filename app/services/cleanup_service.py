from pathlib import Path
import time
class CleanupService:
    def clean(self,root,age_seconds=1800):
        now=time.time(); count=0
        for p in Path(root).rglob('*'):
            if p.is_file() and now-p.stat().st_mtime>age_seconds:
                try:p.unlink();count+=1
                except OSError:pass
        return count
