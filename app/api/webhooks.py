from fastapi import APIRouter,Request,HTTPException
from app.services.webhook_service import verify_signature,payload_hash
router=APIRouter()
@router.post('/webhooks/github')
async def github_webhook(request:Request):
 body=await request.body(); sig=request.headers.get('x-hub-signature-256');
 if not verify_signature(body,sig): raise HTTPException(401,'Invalid webhook signature')
 return {'accepted':True,'delivery_id':request.headers.get('x-github-delivery'),'event':request.headers.get('x-github-event'),'payload_hash':payload_hash(body)}
