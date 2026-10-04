import logging
from .redaction import redact
class RedactingFormatter(logging.Formatter):
    def format(self, record):
        return redact(super().format(record))
def setup_logging(level="INFO"):
    root=logging.getLogger(); root.setLevel(level)
    if not root.handlers:
        h=logging.StreamHandler(); h.setFormatter(RedactingFormatter('%(asctime)s %(levelname)s %(name)s %(message)s')); root.addHandler(h)
