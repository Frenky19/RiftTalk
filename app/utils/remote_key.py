from fastapi import Header, HTTPException, status

from app.config import settings


async def require_client_key(x_rift_client_key: str = Header(default='')):
    expected = settings.RIFT_SHARED_KEY or ''
    if not expected or x_rift_client_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Invalid client key'
        )
