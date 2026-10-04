from fastapi import APIRouter,Request,HTTPException
from fastapi.responses import StreamingResponse
from app.utils.security import verify_value
from app.database.repository import get_connection
from app.utils.security import decrypt
from app.config import settings
from app.github.client import GitHubClient
import base64, json

router=APIRouter()

@router.get('/download/{token}')
async def download(token:str,request:Request):
    if not settings.artifact_signing_secret:
        raise HTTPException(503,'Artifact download service is not configured')
    raw=verify_value(token,settings.artifact_signing_secret)
    if not raw:
        raise HTTPException(403,'Expired or invalid download link')
    try:
        raw += '=' * (-len(raw) % 4)
        data=json.loads(base64.urlsafe_b64decode(raw.encode()).decode())
        owner,repo,artifact_id,user_id=data['o'],data['r'],int(data['a']),int(data['u'])
    except Exception:
        raise HTTPException(403,'Invalid artifact token')
    conn=await get_connection(user_id)
    if not conn:
        raise HTTPException(401,'GitHub connection is no longer active')
    gh=GitHubClient(decrypt(conn.encrypted_pat,settings.encryption_key))
    try:
        response=await gh.artifact_response(owner,repo,artifact_id)
        content=response.content
        return StreamingResponse(iter([content]),media_type='application/zip',headers={
            'Content-Disposition':f'attachment; filename="artifact-{artifact_id}.zip"',
            'Content-Length':str(len(content)),
        })
    except Exception as exc:
        raise HTTPException(404,f'GitHub artifact download failed: {str(exc)[:300]}')
    finally:
        await gh.close()
