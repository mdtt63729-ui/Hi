"""Short-lived artifact callback registry.

Telegram callback_data is limited to 64 bytes, while a signed download token
is much longer. This tiny TTL registry bridges the two without exposing a PAT.
"""
import secrets, time

_ITEMS = {}
_TTL = 1800


def put(owner, repo, artifact_id, user_id, signed_token):
    key = secrets.token_urlsafe(8).replace("-", "_").replace("+", "_")
    _ITEMS[key] = (time.time() + _TTL, owner, repo, int(artifact_id), int(user_id), signed_token)
    _purge()
    return key


def get(key):
    _purge()
    item = _ITEMS.get(key)
    if not item or item[0] < time.time():
        return None
    return item


def _purge():
    now = time.time()
    for k, v in list(_ITEMS.items()):
        if v[0] < now:
            _ITEMS.pop(k, None)
