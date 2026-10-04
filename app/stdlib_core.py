"""Stdlib core helpers used by the TheHostServer-safe Gitofy runtime."""
from __future__ import annotations
import base64, hashlib, hmac, os, re, secrets, time, zipfile
from pathlib import Path
from typing import Iterable


def secure_filename(name: str) -> str:
    name=name.replace('\\','/').strip('/')
    parts=[p for p in name.split('/') if p not in ('','.','..')]
    return '/'.join(parts)


def zip_manifest(path: str|Path, max_files=10000, max_unpacked=500*1024*1024):
    z=zipfile.ZipFile(path)
    names=[]; total=0
    for i in z.infolist():
        n=i.filename
        if n.startswith('/') or '\\' in n or '..' in Path(n).parts:
            raise ValueError('unsafe ZIP path traversal')
        mode=(i.external_attr>>16)&0xffff
        if mode and (mode&0o170000)==0o120000:
            raise ValueError('symlink entries are not allowed')
        names.append(n); total += i.file_size
        if len(names)>max_files: raise ValueError('too many ZIP entries')
        if total>max_unpacked: raise ValueError('extracted-size limit exceeded')
    return z,names,total


def detect_root(names: Iterable[str]):
    files=[n for n in names if n and not n.endswith('/')]
    if not files:return '.'
    tops={n.split('/',1)[0] for n in files if '/' in n}
    if len(tops)==1 and all(n.startswith(next(iter(tops))+'/') for n in files):return next(iter(tops))
    return '.'


def project_detection(names: Iterable[str]):
    low=[n.lower() for n in names]
    return {
      'root':detect_root(names),
      'android': any(n.endswith('androidmanifest.xml') for n in low) or any('com.android.application' in n for n in low),
      'gradle': any(n.endswith(('.gradle','.gradle.kts')) for n in low),
      'kotlin': any(n.endswith('.kt') for n in low),
      'java': any(n.endswith('.java') for n in low),
      'python': any(n.endswith('.py') for n in low),
      'node': any(n.endswith('package.json') for n in low),
    }


def signed_token(secret: str, payload: str, ttl=900):
    exp=int(time.time())+ttl; body=f'{exp}.{payload}'
    sig=hmac.new(secret.encode(),body.encode(),hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f'{body}.{sig}'.encode()).decode().rstrip('=')


def verify_token(secret: str, token: str):
    raw=base64.urlsafe_b64decode(token+'='*((4-len(token)%4)%4)).decode();exp,payload,sig=raw.rsplit('.',2)
    body=f'{exp}.{payload}'
    if int(exp)<int(time.time()): raise ValueError('expired token')
    if not hmac.compare_digest(sig,hmac.new(secret.encode(),body.encode(),hashlib.sha256).hexdigest()):raise ValueError('invalid token')
    return payload
