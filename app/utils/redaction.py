import re
PATTERNS=[re.compile(r'gh[pousr]_[A-Za-z0-9_\-]{20,}'),re.compile(r'(?i)(authorization\s*:\s*bearer\s+)[^\s]+'),re.compile(r'(?i)(bot_token|api[_-]?key|password|secret|encryption[_-]?key)\s*[=:]\s*[^\s,]+')]
def redact(value):
    s=str(value)
    for p in PATTERNS: s=p.sub('[REDACTED]',s)
    return s
