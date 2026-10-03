"""Safe HTTP projection; frontend supports structured detail.message."""
from datetime import datetime, timezone
from math import ceil
from fastapi import HTTPException
from app.core.safe_errors import safe_failure

def safe_http_error(exc, status_code, *, default='unknown'):
    category,message,retry_at=safe_failure(exc,default=default)
    headers=None
    if retry_at:
        status_code=429
        seconds=max(1,ceil((datetime.fromisoformat(retry_at)-datetime.now(timezone.utc)).total_seconds()))
        headers={'Retry-After':str(seconds)}
    return HTTPException(status_code,detail={'category':category,'message':message,'retry_at':retry_at},headers=headers)
