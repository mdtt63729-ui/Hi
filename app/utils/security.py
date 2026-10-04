import base64, hashlib, hmac, time
from cryptography.fernet import Fernet

def make_fernet(key:str)->Fernet:
    if not key: raise RuntimeError('ENCRYPTION_KEY is required')
    try: return Fernet(key.encode())
    except Exception: return Fernet(base64.urlsafe_b64encode(hashlib.sha256(key.encode()).digest()))
def encrypt(value,key): return make_fernet(key).encrypt(value.encode()).decode()
def decrypt(value,key): return make_fernet(key).decrypt(value.encode()).decode()
def sign_value(value,secret,ttl=900):
    exp=int(time.time())+ttl; payload=f'{value}:{exp}'; sig=hmac.new(secret.encode(),payload.encode(),hashlib.sha256).hexdigest(); return f'{payload}:{sig}'
def verify_value(token,secret):
    try:
        value,exp,sig=token.rsplit(':',2)
        if int(exp)<int(time.time()): return None
        payload=f'{value}:{exp}'; expected=hmac.new(secret.encode(),payload.encode(),hashlib.sha256).hexdigest()
        return value if hmac.compare_digest(sig,expected) else None
    except Exception: return None
