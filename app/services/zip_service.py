from pathlib import Path
from zipfile import ZipFile, BadZipFile
import os, stat
from app.config import settings
from app.utils.errors import OperationError
class ZipService:
    def validate(self,path):
        p=Path(path)
        if p.stat().st_size>settings.max_zip_bytes: raise OperationError('ZIP is too large.','zip_too_large')
        try: z=ZipFile(p)
        except BadZipFile: raise OperationError('The uploaded ZIP is corrupted.','corrupt_zip')
        if len(z.infolist())>settings.max_files: raise OperationError('ZIP contains too many files.','too_many_files')
        total=0
        for i in z.infolist():
            n=i.filename.replace('\\','/')
            if n.startswith('/') or n.startswith('../') or '/..' in n.split('/') or '\x00' in n: raise OperationError('Unsafe ZIP path detected.','path_traversal')
            mode=(i.external_attr>>16)&0xffff
            if stat.S_ISLNK(mode): raise OperationError('Symlinks are not allowed in ZIP uploads.','symlink')
            total+=i.file_size
            if total>settings.max_extracted_bytes: raise OperationError('Expanded ZIP exceeds the safety limit.','archive_bomb')
        return True
    def detect_root(self,z):
        names=[x.filename.replace('\\','/').lstrip('/') for x in z.infolist() if x.filename and not x.is_dir()]
        tops={n.split('/')[0] for n in names}
        return next(iter(tops)) if len(tops)==1 and all('/' in n for n in names) else ''
    def extract(self,path,dest):
        self.validate(path); dest=Path(dest); dest.mkdir(parents=True,exist_ok=True)
        with ZipFile(path) as z:
            root=self.detect_root(z)
            for i in z.infolist():
                n=i.filename.replace('\\','/').lstrip('/')
                if root and n.startswith(root+'/'): n=n[len(root)+1:]
                target=(dest/n).resolve()
                if dest.resolve() not in target.parents and target!=dest.resolve(): raise OperationError('Unsafe extraction path.','path_traversal')
                if i.is_dir(): target.mkdir(parents=True,exist_ok=True); continue
                target.parent.mkdir(parents=True,exist_ok=True)
                with z.open(i) as src, open(target,'wb') as out:
                    while True:
                        chunk=src.read(1024*1024)
                        if not chunk: break
                        out.write(chunk)
        return dest
