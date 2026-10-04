import os, tempfile, zipfile, json
from pathlib import Path
os.environ.setdefault('GITOFY_DATA_DIR', tempfile.mkdtemp())
os.environ['GITOFY_ENCRYPTION_KEY']='test-secret'
import importlib.util
spec=importlib.util.spec_from_file_location('gitofy_bot',str(Path(__file__).parents[1]/'bot.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def test_pat_encryption_roundtrip():
    x='ghp_example_NOT_REAL'; y=m.protect_pat(x); assert y.startswith('gse1:'); assert m.unprotect_pat(y)==x

def test_progress_is_github_derived():
    run={'id':1,'name':'Build','head_branch':'main','status':'in_progress','conclusion':None}
    jobs=[{'name':'build','status':'completed','conclusion':'success','steps':[{'name':'checkout','status':'completed','conclusion':'success'},{'name':'compile','status':'in_progress','conclusion':None}] }]
    _,pct,done,total=m.Progress.render(run,jobs); assert (done,total)==(1,2); assert pct==50

def test_zip_traversal_rejected():
    fd,path=tempfile.mkstemp(suffix='.zip');os.close(fd)
    with zipfile.ZipFile(path,'w') as z:z.writestr('../evil.txt','x')
    try:
        try:m.validate_zip(path);assert False
        except m.GitofyError:pass
    finally:os.unlink(path)
