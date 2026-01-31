import logging

from fastapi import APIRouter, Depends, HTTPException

from app.services.remote_api import RemoteAPIError, remote_api
from app.utils.security import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/voice', tags=['voice-client'])


@router.post('/reconnect')
async def reconnect_voice(current_user: dict = Depends(get_current_user)):
    """Proxy reconnect request to the remote server."""
    try:
        summoner_id = str(current_user.get('sub') or '')
        if not summoner_id:
            raise HTTPException(status_code=401, detail='Not authenticated')
        try:
            return await remote_api.voice_reconnect({'summoner_id': summoner_id})
        except RemoteAPIError as e:
            raise HTTPException(status_code=502, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f'Reconnect failed: {e}')
        raise HTTPException(status_code=500, detail='Reconnect failed')
