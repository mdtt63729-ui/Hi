class OperationError(Exception):
    def __init__(self, message, code='internal_error', retryable=False, status=None):
        super().__init__(message); self.code=code; self.retryable=retryable; self.status=status
