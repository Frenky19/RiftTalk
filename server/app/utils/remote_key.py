import hashlib
import hmac
import time

from fastapi import Header, HTTPException, Request, status

from app.config import settings


async def require_client_key(
    request: Request,
    x_rift_client_key: str = Header(default=''),
    x_rift_timestamp: str = Header(default=''),
    x_rift_signature: str = Header(default=''),
):
    expected = settings.RIFT_SHARED_KEY or ''
    if not expected or x_rift_client_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Invalid client key'
        )

    if getattr(settings, 'RIFT_SIGNATURE_ENABLED', True):
        if not x_rift_timestamp or not x_rift_signature:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail='Missing request signature'
            )
        try:
            ts = int(x_rift_timestamp)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail='Invalid request timestamp'
            )
        now = int(time.time())
        ttl = int(getattr(settings, 'RIFT_SIGNATURE_TTL_SECONDS', 60) or 60)
        if abs(now - ts) > ttl:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail='Request timestamp out of range'
            )
        body_bytes = await request.body()
        body_hash = hashlib.sha256(body_bytes or b'').hexdigest()
        path = request.url.path
        if request.url.query:
            path = f'{path}?{request.url.query}'
        message = f'{ts}\n{request.method.upper()}\n{path}\n{body_hash}'
        expected_sig = hmac.new(
            expected.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected_sig, x_rift_signature):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail='Invalid request signature'
            )
