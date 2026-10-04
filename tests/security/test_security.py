from app.services.webhook_service import payload_hash
from app.utils.redaction import redact
def test_redaction(): assert 'ghp_' not in redact('ghp_'+'A'*30)
def test_hash(): assert len(payload_hash(b'abc'))==64
