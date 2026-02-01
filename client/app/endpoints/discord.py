import json
import logging
import time

from fastapi import APIRouter, Depends, HTTPException, status

from app.constants import (
    MATCH_INFO_TTL_SECONDS,
    MATCH_STATUS_REMOTE_REFRESH_SECONDS,
)
from app.database import redis_manager
from app.services.lcu_service import lcu_service
from app.services.remote_api import RemoteAPIError, remote_api
from app.utils.security import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/discord', tags=['discord-client'])

def _decode_redis_value(value):
    """Decode bytes values returned by Redis into UTF-8 strings."""
    if isinstance(value, (bytes, bytearray)):
        return value.decode('utf-8', errors='ignore')
    return value


def _decode_redis_hash(data):
    """Decode a Redis hash to a plain dict with string keys/values."""
    decoded = {}
    for key, value in (data or {}).items():
        decoded[_decode_redis_value(key)] = _decode_redis_value(value)
    return decoded


def _parse_bool(value):
    """Parse common truthy values into a bool."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on')


def _parse_json(value):
    """Parse JSON strings into Python types, return original on failure."""
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str) and value.strip() != '':
        try:
            return json.loads(value)
        except Exception:
            return value
    return value


@router.get('/linked-account')
async def get_linked_discord_account(
    current_user: dict = Depends(get_current_user)
):
    try:
        summoner_id = str(current_user['sub'])
        return await remote_api.linked_account(summoner_id)
    except RemoteAPIError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))


@router.get('/user-server-status/{discord_user_id}')
async def check_user_server_status(
    discord_user_id: str,
    current_user: dict = Depends(get_current_user)
):
    try:
        return await remote_api.user_server_status(str(discord_user_id))
    except RemoteAPIError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))


@router.get('/user-match-info/{summoner_id}')
async def get_user_match_info(
    summoner_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Best-effort local match info for compatibility."""
    try:
        if str(current_user.get('sub')) != str(summoner_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Forbidden')
        match_info_key = f'user_match:{summoner_id}'
        match_id = _decode_redis_value(
            await redis_manager.redis.hget(match_info_key, 'match_id')
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
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Failed to get user match info',
        )


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

        match_info_key = f'user_match:{summoner_id}'
        cached = {}
        try:
            cached = _decode_redis_hash(await redis_manager.redis.hgetall(match_info_key))
        except Exception:
            cached = {}

        now_ts = time.time()
        cache_match_id = cached.get('match_id')
        cache_ts_raw = cached.get('remote_status_cached_at', '0') or '0'
        try:
            cache_ts = float(cache_ts_raw)
        except Exception:
            cache_ts = 0.0

        use_cache = (
            cache_match_id == match_id
            and cache_ts > 0
            and (now_ts - cache_ts) < MATCH_STATUS_REMOTE_REFRESH_SECONDS
        )

        try:
            if use_cache:
                remote = {
                    'match_id': cache_match_id,
                    'team_name': cached.get('remote_team_name'),
                    'voice_channel': _parse_json(cached.get('remote_voice_channel')),
                    'linked': _parse_bool(cached.get('remote_linked')),
                    'assigned': _parse_bool(cached.get('remote_assigned')),
                }
            else:
                remote = await remote_api.match_start(payload)
                try:
                    await redis_manager.redis.hset(
                        match_info_key,
                        mapping={
                            'match_id': match_id,
                            'remote_team_name': str(remote.get('team_name') or ''),
                            'remote_voice_channel': json.dumps(
                                remote.get('voice_channel')
                            ) if remote.get('voice_channel') is not None else '',
                            'remote_linked': '1' if remote.get('linked') else '0',
                            'remote_assigned': '1' if remote.get('assigned') else '0',
                            'remote_status_cached_at': str(now_ts),
                        },
                    )
                    await redis_manager.redis.expire(
                        match_info_key,
                        MATCH_INFO_TTL_SECONDS,
                    )
                except Exception:
                    pass
        except RemoteAPIError as e:
            if cache_match_id == match_id and cached:
                remote = {
                    'match_id': cache_match_id,
                    'team_name': cached.get('remote_team_name'),
                    'voice_channel': _parse_json(cached.get('remote_voice_channel')),
                    'linked': _parse_bool(cached.get('remote_linked')),
                    'assigned': _parse_bool(cached.get('remote_assigned')),
                }
            else:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=str(e),
                )

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
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Failed to get match status',
        )
