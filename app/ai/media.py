"""Safe Telegram attachment preparation for the AI team."""
import mimetypes, os, zipfile
from pathlib import Path

MAX_INLINE_BYTES=12*1024*1024
MAX_TEXT_CHARS=120000
TEXT_EXT={'.txt','.md','.json','.xml','.yaml','.yml','.toml','.ini','.cfg','.properties','.gradle','.kts','.kt','.java','.py','.js','.ts','.tsx','.jsx','.css','.html','.csv','.sql','.sh','.bat','.log','.diff','.patch','.env'}

def text_from_bytes(name,data):
    ext=Path(name or '').suffix.lower()
    if ext not in TEXT_EXT and not (name or '').lower().endswith(('requirements.txt','Dockerfile','Makefile')):
        return None
    return data.decode('utf-8',errors='replace')[:MAX_TEXT_CHARS]

def zip_manifest(data):
    try:
        with zipfile.ZipFile(__import__('io').BytesIO(data)) as z:
            names=z.namelist()[:500]
        return '\n'.join(names)
    except Exception: return None

def make_part(name,data,mime=None):
    mime=mime or mimetypes.guess_type(name or '')[0] or 'application/octet-stream'
    text=text_from_bytes(name,data)
    if text is not None: return {'kind':'text','name':name,'mime':mime,'text':text}
    if mime.startswith('image/') and len(data)<=MAX_INLINE_BYTES:
        return {'kind':'image','name':name,'mime':mime,'data':data}
    if (name or '').lower().endswith('.zip'):
        manifest=zip_manifest(data)
        return {'kind':'text','name':name,'mime':mime,'text':'ZIP file manifest:\n'+(manifest or '(unreadable)')}
    if len(data)<=MAX_INLINE_BYTES and mime.startswith(('video/','audio/')):
        return {'kind':'binary','name':name,'mime':mime,'data':data}
    return {'kind':'text','name':name,'mime':mime,'text':f'Binary attachment: {name} ({len(data):,} bytes). Raw binary is not embedded; inspect available metadata and ask for a supported conversion if needed.'}
