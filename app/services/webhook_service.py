import hashlib,hmac,json
from app.config import settings
def verify_signature(body,signature):
    if not settings.webhook_secret: return False
    expected='sha256='+hmac.new(settings.webhook_secret.encode(),body,hashlib.sha256).hexdigest(); return hmac.compare_digest(expected,signature or '')
def payload_hash(body): return hashlib.sha256(body).hexdigest()
