from pathlib import Path
import hashlib
def files_map(root):
    out={}
    for p in Path(root).rglob('*'):
        if p.is_file(): out[str(p.relative_to(root)).replace('\\','/')]=hashlib.sha256(p.read_bytes()).hexdigest()
    return out
def compare(uploaded,repo):
    a,b=files_map(uploaded),repo
    return {'added':sorted(set(a)-set(b)),'modified':sorted(k for k in set(a)&set(b) if a[k]!=b[k]),'deleted':sorted(set(b)-set(a)),'unchanged':sorted(k for k in set(a)&set(b) if a[k]==b[k])}
