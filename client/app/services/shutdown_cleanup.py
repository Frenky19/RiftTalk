import asyncio
import logging
from typing import Optional, Tuple

from app.config import settings
from app.database import redis_manager
from app.services.lcu_service import lcu_service
from app.services.remote_api import RemoteAPIError, remote_api

logger = logging.getLogger(__name__)


def _decode_redis_value(value):
    if isinstance(value, (bytes, bytearray)):
        return value.decode('utf-8', errors='ignore')
    return value


def _decode_redis_hash(data: dict) -> dict:
    decoded = {}
    for key, value in (data or {}).items():
        decoded[_decode_redis_value(key)] = _decode_redis_value(value)
    return decoded


async def _resolve_shutdown_match_context(
    allow_lcu: bool = True,
) -> Tuple[Optional[str], Optional[str]]:
    """Best-effort resolve (summoner_id, match_id) for shutdown cleanup."""
    summoner_id = None
    match_id = None

    # 1) Prefer LCU if still connected.
    if allow_lcu:
        try:
            if (
                getattr(lcu_service, 'lcu_connector', None)
                and lcu_service.lcu_connector.is_connected()
            ):
                current_summoner = await lcu_service.lcu_connector.get_current_summoner()
                if current_summoner and current_summoner.get('summonerId'):
                    summoner_id = str(current_summoner.get('summonerId'))
        except Exception:
            pass

    # 2) If we know summoner_id, check direct keys.
    if summoner_id:
        try:
            match_id = _decode_redis_value(
                await redis_manager.redis.hget(f'user:{summoner_id}', 'current_match')
            )
        except Exception:
            match_id = None
        if not match_id:
            try:
                match_id = _decode_redis_value(
                    await redis_manager.redis.hget(
                        f'user_match:{summoner_id}', 'match_id'
                    )
                )
            except Exception:
                match_id = None

    # 3) Scan user:* keys for an active current_match.
    if not summoner_id or not match_id:
        try:
            for key in await redis_manager.redis.scan_iter(match='user:*'):
                key = _decode_redis_value(key)
                if not str(key).startswith('user:'):
                    continue
                user_data = _decode_redis_hash(
                    await redis_manager.redis.hgetall(key) or {}
                )
                current_match = user_data.get('current_match')
                if current_match:
                    summoner_id = user_data.get('summoner_id') or str(key).split(
                        'user:', 1
                    )[1]
                    match_id = current_match
                    break
        except Exception:
            pass

    # 4) Scan user_match:* keys if still missing.
    if not match_id or not summoner_id:
        try:
            for key in await redis_manager.redis.scan_iter(match='user_match:*'):
                key = _decode_redis_value(key)
                if not str(key).startswith('user_match:'):
                    continue
                user_match = _decode_redis_hash(
                    await redis_manager.redis.hgetall(key) or {}
                )
                candidate = user_match.get('match_id')
                if candidate:
                    match_id = candidate
                    if not summoner_id:
                        summoner_id = str(key).split('user_match:', 1)[1]
                    break
        except Exception:
            pass

    # 5) Last-resort: attempt to derive match_id from current session.
    if allow_lcu and summoner_id and not match_id:
        try:
            if (
                getattr(lcu_service, 'lcu_connector', None)
                and lcu_service.lcu_connector.is_connected()
            ):
                session = await lcu_service.lcu_connector.get_current_session()
                game_id = None
                if session:
                    game_id = session.get('gameData', {}).get('gameId')
                if game_id:
                    match_id = f'match_{game_id}'
        except Exception:
            pass

    return (
        str(summoner_id) if summoner_id else None,
        str(match_id) if match_id else None,
    )


async def notify_match_leave_on_shutdown(
    allow_lcu: bool = True,
    timeout_seconds: int = 5,
) -> None:
    """Best-effort notify remote server if the app closes mid-match."""
    if not settings.is_client:
        return

    summoner_id, match_id = await _resolve_shutdown_match_context(
        allow_lcu=allow_lcu
    )
    if not summoner_id or not match_id:
        return

    try:
        await asyncio.wait_for(
            remote_api.match_leave(
                {'match_id': str(match_id), 'summoner_id': str(summoner_id)}
            ),
            timeout=timeout_seconds,
        )
    except RemoteAPIError as e:
        logger.warning(f'Remote match-leave (shutdown) failed: {e}')
    except asyncio.TimeoutError:
        logger.warning('Remote match-leave (shutdown) timed out')

    # Local cleanup of pointers (best-effort).
    try:
        await redis_manager.redis.hdel(f'user:{summoner_id}', 'current_match')
    except Exception:
        pass
