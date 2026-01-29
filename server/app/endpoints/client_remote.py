import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException

from app.database import redis_manager
from app.services.discord_service import discord_service
from app.services.voice_service import voice_service
from app.utils.remote_key import require_client_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/client", tags=["client-remote"])


def _get_team_name(summoner_id: str, blue_team: List[str], red_team: List[str]) -> Optional[str]:
    sid = str(summoner_id)
    if sid in [str(x) for x in (blue_team or [])]:
        return "Blue Team"
    if sid in [str(x) for x in (red_team or [])]:
        return "Red Team"
    return None


def _parse_discord_channels(room_data: Dict[str, Any]) -> Dict[str, Any]:
    discord_channels = room_data.get("discord_channels")
    try:
        if isinstance(discord_channels, str):
            discord_channels = json.loads(discord_channels)
    except Exception:
        pass
    return discord_channels or {}


def _get_discord_user_id(summoner_id: str) -> Optional[str]:
    user_key = f"user:{summoner_id}"
    try:
        user_data = redis_manager.redis.hgetall(user_key) or {}
        discord_user_id = user_data.get("discord_user_id")
        if discord_user_id:
            return str(discord_user_id)
    except Exception:
        pass
    return None


def _acquire_lock(key: str, ttl_seconds: int) -> bool:
    """
    Cross-backend lock:
    - If real Redis: SET key value NX EX ttl
    - If MemoryStorage (no nx/ex): emulate NX via GET+SET best-effort.
    IMPORTANT: MemoryStorage lock is per-process only (fine for localhost single process).
    """
    r = redis_manager.redis

    # Real Redis path
    try:
        # If this works, we're on real redis-py like client
        res = r.set(key, "1", nx=True, ex=ttl_seconds)
        return bool(res)
    except TypeError:
        # MemoryStorage path (no nx/ex)
        pass
    except Exception as e:
        logger.warning(f"Lock acquire failed (redis-style) for {key}: {e}")

    # Best-effort NX emulation
    try:
        existing = r.get(key)
        if existing is not None:
            return False
    except Exception:
        # If backend doesn't support get, we can't safely emulate
        return True

    # Try to set with TTL if supported by backend
    try:
        r.set(key, "1")
    except Exception as e:
        logger.warning(f"Lock set failed for {key}: {e}")
        return True

    # Try best-effort expiration (some storages may support expire)
    try:
        r.expire(key, ttl_seconds)
    except Exception:
        pass

    return True


@router.post("/match-start")
async def client_match_start(payload: Dict[str, Any], _: Any = Depends(require_client_key)):
    """
    Client notifies server that match is InProgress.

    Expected payload:
      - match_id (match_<gameId>)
      - summoner_id
      - summoner_name
      - blue_team: [summonerId...]
      - red_team: [summonerId...]
    """
    match_id = str(payload.get("match_id") or "")
    summoner_id = str(payload.get("summoner_id") or "")
    summoner_name = str(payload.get("summoner_name") or "Unknown")
    blue_team = payload.get("blue_team") or []
    red_team = payload.get("red_team") or []

    if not match_id or not match_id.startswith("match_"):
        raise HTTPException(status_code=400, detail="Invalid match_id")
    if not summoner_id:
        raise HTTPException(status_code=400, detail="Missing summoner_id")

    team_name = _get_team_name(summoner_id, blue_team, red_team)

    # --- Anti-spam / idempotency guards ---
    # 1) Per-player debounce (prevents role spam & race conditions due to frequent polling)
    player_lock_key = f"lock:matchstart:{match_id}:{summoner_id}"
    got_player_lock = _acquire_lock(player_lock_key, ttl_seconds=10)

    if not got_player_lock:
        room_data = redis_manager.get_voice_room_by_match(match_id) or {}
        discord_channels = _parse_discord_channels(room_data)

        discord_user_id = _get_discord_user_id(summoner_id)

        voice_channel = None
        if team_name == "Blue Team":
            voice_channel = discord_channels.get("blue_team")
        elif team_name == "Red Team":
            voice_channel = discord_channels.get("red_team")

        return {
            "match_id": match_id,
            "match_started": True,
            "in_progress": True,
            "team_name": team_name,
            "voice_channel": voice_channel,
            "linked": bool(discord_user_id),
            "assigned": False,
            "summoner_name": summoner_name,
            "debounced": True,
        }

    # 2) Per-match room creation lock (only one creator at a time)
    room_lock_key = f"lock:roomcreate:{match_id}"
    got_room_lock = _acquire_lock(room_lock_key, ttl_seconds=30)

    if got_room_lock:
        all_players = [str(x) for x in (blue_team + red_team)]
        await voice_service.create_or_get_voice_room(
            match_id, all_players, {"blue_team": blue_team, "red_team": red_team}
        )
    else:
        # Another request is likely creating it. Wait briefly until room appears.
        for _ in range(10):  # up to ~1s
            if redis_manager.get_voice_room_by_match(match_id):
                break
            await asyncio.sleep(0.1)

    room_data = redis_manager.get_voice_room_by_match(match_id) or {}
    discord_channels = _parse_discord_channels(room_data)

    # Linked discord?
    discord_user_id = _get_discord_user_id(summoner_id)

    assigned = False
    if discord_user_id and team_name:
        try:
            assigned = await discord_service.assign_player_to_team(int(discord_user_id), match_id, team_name)
            # If the user is already in voice (e.g. Waiting Room), move them to their team channel
            await discord_service.move_member_to_team_channel_if_in_voice(int(discord_user_id), match_id, team_name)
        except Exception as e:
            logger.warning(f"Assign failed for {discord_user_id}: {e}")

    voice_channel = None
    if team_name == "Blue Team":
        voice_channel = discord_channels.get("blue_team")
    elif team_name == "Red Team":
        voice_channel = discord_channels.get("red_team")

    return {
        "match_id": match_id,
        "match_started": True,
        "in_progress": True,
        "team_name": team_name,
        "voice_channel": voice_channel,
        "linked": bool(discord_user_id),
        "assigned": bool(assigned),
        "summoner_name": summoner_name,
        "debounced": False,
    }


@router.post("/match-end")
async def client_match_end(payload: Dict[str, Any], _: Any = Depends(require_client_key)):
    match_id = str(payload.get("match_id") or "")
    if not match_id:
        raise HTTPException(status_code=400, detail="Missing match_id")

    try:
        await discord_service.cleanup_match_channels({"match_id": match_id})
    except Exception as e:
        logger.warning(f"Discord cleanup failed: {e}")

    try:
        redis_manager.delete_voice_room(match_id)
    except Exception as e:
        logger.warning(f"Room delete failed: {e}")

    return {"ok": True, "match_id": match_id}


@router.post("/match-leave")
async def client_match_leave(payload: Dict[str, Any], _: Any = Depends(require_client_key)):
    match_id = str(payload.get("match_id") or "")
    summoner_id = str(payload.get("summoner_id") or "")
    if not match_id or not summoner_id:
        raise HTTPException(status_code=400, detail="Missing match_id or summoner_id")

    discord_user_id = _get_discord_user_id(summoner_id)

    if discord_user_id:
        try:
            await voice_service.handle_player_left_match(match_id, summoner_id, int(discord_user_id))
        except Exception as e:
            logger.warning(f"handle_player_left_match failed: {e}")
            return {"ok": False, "error": str(e)}

    return {"ok": True}


@router.post("/voice-reconnect")
async def client_voice_reconnect(payload: Dict[str, Any], _: Any = Depends(require_client_key)):
    """Reconnect a user to their match role/channel on the server side."""
    summoner_id = str(payload.get("summoner_id") or "")
    if not summoner_id:
        raise HTTPException(status_code=400, detail="Missing summoner_id")

    match_id = voice_service.get_active_match_id_for_summoner(summoner_id)
    if not match_id:
        try:
            active_rooms = voice_service.redis.get_all_active_rooms()
            for room in active_rooms:
                blue = voice_service.safe_json_parse(room.get("blue_team"), []) or []
                red = voice_service.safe_json_parse(room.get("red_team"), []) or []
                if summoner_id in blue or summoner_id in red:
                    match_id = room.get("match_id")
                    break
        except Exception:
            match_id = None

    if not match_id:
        raise HTTPException(status_code=404, detail="Active match not found")

    room_data = voice_service.redis.get_voice_room_by_match(match_id)
    if not room_data:
        raise HTTPException(status_code=404, detail="Voice room not found")

    blue = voice_service.safe_json_parse(room_data.get("blue_team"), []) or []
    red = voice_service.safe_json_parse(room_data.get("red_team"), []) or []
    if summoner_id in blue:
        team_name = "Blue Team"
    elif summoner_id in red:
        team_name = "Red Team"
    else:
        raise HTTPException(status_code=404, detail="Player not found in room teams")

    discord_user_id = _get_discord_user_id(summoner_id)
    if not discord_user_id:
        raise HTTPException(status_code=409, detail="Discord is not linked for this summoner")

    try:
        discord_user_id_int = int(discord_user_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid discord_user_id")

    assigned = await discord_service.assign_player_to_team(
        discord_user_id=discord_user_id_int,
        match_id=match_id,
        team_name=team_name,
    )
    moved = await discord_service.move_member_to_team_channel_if_in_voice(
        discord_user_id=discord_user_id_int,
        match_id=match_id,
        team_name=team_name,
    )

    invite_url = ""
    try:
        channel = await discord_service.create_or_get_voice_channel(match_id, team_name)
        invite_url = (channel or {}).get("invite_url", "") or ""
    except Exception:
        invite_url = ""

    return {
        "status": "ok",
        "match_id": match_id,
        "team_name": team_name,
        "role_assigned": bool(assigned),
        "moved_if_in_voice": bool(moved),
        "invite_url": invite_url,
        "note": (
            "If you were not connected to voice, use invite_url or join Waiting Room and press reconnect again."
        ),
    }
