import logging
from fastapi import APIRouter, HTTPException, Depends

from app.database import redis_manager
from app.services.lcu_service import lcu_service
from app.services.remote_api import remote_api, RemoteAPIError
from app.utils.security import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/discord', tags=['discord-client'])


def _decode_redis_value(value):
    if isinstance(value, (bytes, bytearray)):
        return value.decode('utf-8', errors='ignore')
    return value


@router.get('/linked-account')
async def get_linked_discord_account(
    current_user: dict = Depends(get_current_user)
):
    try:
        summoner_id = str(current_user['sub'])
        return await remote_api.linked_account(summoner_id)
    except RemoteAPIError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get('/user-server-status/{discord_user_id}')
async def check_user_server_status(
    discord_user_id: str,
    current_user: dict = Depends(get_current_user)
):
    try:
        return await remote_api.user_server_status(str(discord_user_id))
    except RemoteAPIError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get('/user-match-info/{summoner_id}')
async def get_user_match_info(
    summoner_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Best-effort local match info for compatibility."""
    try:
        if str(current_user.get('sub')) != str(summoner_id):
            raise HTTPException(status_code=403, detail='Forbidden')
        match_info_key = f'user_match:{summoner_id}'
        match_id = _decode_redis_value(
            redis_manager.redis.hget(match_info_key, 'match_id')
        )
        return {
            'match_id': match_id,
            'team_name': None,
            'voice_channel': None
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f'Failed to get user match info: {e}')
        raise HTTPException(status_code=500, detail='Failed to get user match info')


@router.get('/match-status/{summoner_id}')
async def get_match_status(
    summoner_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get user's current match status (client-side view)."""
    try:
        phase = None
        try:
            if lcu_service.lcu_connector.is_connected():
                phase = await lcu_service.lcu_connector.get_game_flow_phase()
        except Exception as e:
            logger.warning(f'LCU phase fetch failed: {e}')

        in_champ_select = phase == 'ChampSelect'
        in_loading_screen = phase == 'LoadingScreen'
        in_progress = phase == 'InProgress'

        if not in_progress:
            return {
                'match_id': None,
                'match_started': False,
                'in_champ_select': bool(in_champ_select),
                'in_loading_screen': bool(in_loading_screen),
                'in_progress': bool(in_progress),
                'voice_channel': None,
            }

        session = await lcu_service.lcu_connector.get_current_session()
        game_id = None
        if session:
            game_id = session.get('gameData', {}).get('gameId')

        if not game_id:
            return {
                'match_id': None,
                'match_started': False,
                'in_champ_select': False,
                'in_loading_screen': False,
                'in_progress': True,
                'voice_channel': None,
            }

        match_id = f'match_{game_id}'

        teams_data = await lcu_service.lcu_connector.get_teams()
        blue_team_ids = [
            str(p.get('summonerId'))
            for p in (teams_data or {}).get('blue_team', [])
            if p.get('summonerId')
        ]
        red_team_ids = [
            str(p.get('summonerId'))
            for p in (teams_data or {}).get('red_team', [])
            if p.get('summonerId')
        ]

        payload = {
            'match_id': match_id,
            'summoner_id': str(summoner_id),
            'summoner_name': str(current_user.get('name') or 'Unknown'),
            'blue_team': blue_team_ids,
            'red_team': red_team_ids,
        }

        try:
            remote = await remote_api.match_start(payload)
        except RemoteAPIError as e:
            raise HTTPException(status_code=502, detail=str(e))

        return {
            'match_id': remote.get('match_id') or match_id,
            'match_started': True,
            'in_champ_select': False,
            'in_loading_screen': False,
            'in_progress': True,
            'team_name': remote.get('team_name'),
            'voice_channel': remote.get('voice_channel'),
            'linked': remote.get('linked'),
            'assigned': remote.get('assigned'),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f'Failed to get match status: {e}')
        raise HTTPException(status_code=500, detail='Failed to get match status')
