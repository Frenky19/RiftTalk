"""
Database module with automatic fallback to in-memory storage
"""

import json
import logging
import os
import sys
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional


logger = logging.getLogger(__name__)


def _get_setting(name: str, default: Any = None) -> Any:
    """Best-effort config lookup without forcing app.config import."""
    value = os.getenv(name)
    if value is not None and str(value).strip() != "":
        return value
    try:
        cfg = sys.modules.get("app.config")
        settings = getattr(cfg, "settings", None)
        if settings and hasattr(settings, name):
            return getattr(settings, name)
    except Exception:
        pass
    return default


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in ("1", "true", "yes", "on")


class MemoryStorage:
    """In-Memory storage with Redis-compatible interface"""

    def __init__(self):
        self._data = {}
        self._expiry = {}
        self._lock = threading.RLock()
        logger.info('In-Memory storage initialized')

    def ping(self):
        """Always return True for Redis compatibility"""
        return True

    def hset(self, key: str, *args, **kwargs) -> bool:
        """Set hash value.

        Compatible with redis-py:
        - hset(name, mapping={...})
        - hset(name, field, value)

        Also accepts a dict as the 2nd positional argument for legacy calls.
        """
        mapping = kwargs.get('mapping')
        if mapping is None and len(args) == 1 and isinstance(args[0], dict):
            mapping = args[0]
        if mapping is None and len(args) == 2:
            field, value = args
            mapping = {str(field): value}
        if mapping is None:
            raise TypeError(
                'hset expected either mapping={...}, a dict positional, or (field, value)'
            )
        with self._lock:
            if key not in self._data:
                self._data[key] = {}
            if not isinstance(self._data[key], dict):
                self._data[key] = {}
            self._data[key].update(mapping)
            return True

    def hget(self, key: str, field: str) -> Optional[str]:
        """Get value from hash by field"""
        with self._lock:
            if key in self._data and isinstance(self._data[key], dict):
                return self._data[key].get(field)
            return None

    def hdel(self, name: str, *keys) -> int:
        """Delete one or more hash fields."""
        if name not in self._data or not isinstance(self._data[name], dict):
            return 0
        deleted = 0
        for k in keys:
            if k in self._data[name]:
                del self._data[name][k]
                deleted += 1
        return deleted

    def hgetall(self, key: str) -> Dict[str, Any]:
        """Get all fields from hash"""
        with self._lock:
            if key in self._data and isinstance(self._data[key], dict):
                return self._data[key].copy()
            return {}

    def get(self, key: str) -> Optional[str]:
        """Get value by key"""
        with self._lock:
            # Check expiry
            if key in self._expiry and datetime.now(
                timezone.utc
            ) > self._expiry[key]:
                del self._data[key]
                del self._expiry[key]
                return None
            if key in self._data:
                if isinstance(self._data[key], (dict, list)):
                    return json.dumps(self._data[key])
                return str(self._data[key])
            return None

    def set(
        self,
        key: str,
        value: Any,
        nx: bool = False,
        ex: Optional[int] = None,
        px: Optional[int] = None,
        **kwargs,
    ) -> bool:
        """Redis-like SET for the in-memory fallback.

        This server sometimes runs without a real Redis instance. A few code
        paths rely on Redis' SET options:
        - nx=True: set only if key does not exist
        - ex=<seconds>: expiry in seconds

        We implement the subset needed by the project. Unknown kwargs are
        accepted to stay compatible with redis-py.
        """
        if px is not None and ex is None:
            # Allow passing px (milliseconds) even if callers use redis-py style.
            ex = max(1, int(px / 1000))

        with self._lock:
            # If key exists but is expired, treat it as non-existent.
            if key in self._expiry and self._expiry[key] < datetime.now(timezone.utc):
                self._data.pop(key, None)
                self._expiry.pop(key, None)

            if nx and key in self._data:
                return False

            self._data[key] = value
            if ex is not None:
                self._expiry[key] = datetime.now(timezone.utc) + timedelta(seconds=int(ex))
            else:
                self._expiry.pop(key, None)
            return True

    def setex(self, key: str, time: int, value: Any) -> bool:
        """Set value with expiry"""
        with self._lock:
            self._data[key] = value
            if time > 0:
                self._expiry[key] = (
                    datetime.now(timezone.utc) + timedelta(seconds=time)
                )
            return True

    def expire(self, key: str, time: int) -> bool:
        """Set expiry time for existing key"""
        with self._lock:
            if key in self._data:
                if time > 0:
                    self._expiry[key] = (
                        datetime.now(timezone.utc) + timedelta(seconds=time)
                    )
                else:
                    # If time is 0 or negative, remove expiry
                    if key in self._expiry:
                        del self._expiry[key]
                return True
            return False

    def delete(self, key: str) -> bool:
        """Delete key"""
        with self._lock:
            if key in self._data:
                del self._data[key]
            if key in self._expiry:
                del self._expiry[key]
            return True

    def exists(self, key: str) -> bool:
        """Check if key exists"""
        with self._lock:
            # Check expiry
            if key in self._expiry and datetime.now(
                timezone.utc
            ) > self._expiry[key]:
                del self._data[key]
                del self._expiry[key]
                return False
            return key in self._data

    def scan_iter(self, match: Optional[str] = None):
        """Iterate over keys (simplified version)"""
        with self._lock:
            current_time = datetime.now(timezone.utc)
            # Clean expired keys
            expired_keys = [
                k for k, exp in self._expiry.items() if current_time > exp
            ]
            for key in expired_keys:
                del self._data[key]
                del self._expiry[key]
            # Return keys matching pattern
            for key in list(self._data.keys()):
                if match is None or (match and match.replace('*', '') in key):
                    yield key

    def type(self, key: str) -> str:
        """Determine key type (simplified version)"""
        with self._lock:
            if key not in self._data:
                return 'none'
            if isinstance(self._data[key], dict):
                return 'hash'
            elif isinstance(self._data[key], list):
                return 'list'
            else:
                return 'string'

    def pipeline(self):
        """Return pipeline for batch operations"""
        return MemoryPipeline(self)


class MemoryPipeline:
    """In-Memory pipeline for batch operations"""

    def __init__(self, storage: MemoryStorage):
        self.storage = storage
        self.commands = []

    def hset(self, key: str, *args, **kwargs):
        """Add hset command to pipeline (redis-py compatible)."""
        mapping = kwargs.get('mapping')
        if mapping is None and len(args) == 1 and isinstance(args[0], dict):
            mapping = args[0]
        if mapping is None and len(args) == 2:
            field, value = args
            mapping = {str(field): value}
        if mapping is None:
            raise TypeError(
                'hset expected either mapping={...}, a dict positional, or (field, value)'
            )
        self.commands.append(('hset', key, mapping))
        return self

    def expire(self, key: str, time: int):
        """Add expire command to pipeline"""
        self.commands.append(('expire', key, time))
        return self

    def set(self, key: str, value: Any, ex: Optional[int] = None):
        """Add set command to pipeline"""
        self.commands.append(('set', key, value, ex))
        return self

    def delete(self, key: str):
        """Add delete command to pipeline"""
        self.commands.append(('delete', key))
        return self

    def hdel(self, name: str, *keys):
        """Add hdel command to pipeline"""
        self.commands.append(('hdel', name, keys))
        return self

    def execute(self):
        """Execute all commands in pipeline"""
        results = []
        for command in self.commands:
            try:
                if command[0] == 'hset':
                    result = self.storage.hset(command[1], command[2])
                elif command[0] == 'set':
                    if command[3] is not None:
                        result = self.storage.setex(
                            command[1], command[3], command[2]
                        )
                    else:
                        result = self.storage.set(command[1], command[2])
                elif command[0] == 'delete':
                    result = self.storage.delete(command[1])
                elif command[0] == 'expire':
                    result = self.storage.expire(command[1], command[2])
                elif command[0] == 'hdel':
                    result = self.storage.hdel(command[1], *command[2])
                else:
                    logger.error(f'Unknown command: {command[0]}')
                    result = False
                results.append(result)
            except Exception as e:
                logger.error(f'Pipeline command error: {e}')
                results.append(False)
        self.commands = []
        return results


class DatabaseManager:
    """Mock database manager with RedisManager-compatible interface"""

    def __init__(self):
        self.redis = self._init_storage()
        logger.info('Database Manager initialized')

    def _init_storage(self):
        """Initialize Redis if available, otherwise fallback to memory."""
        redis_url = _get_setting("REDIS_URL", "")
        if redis_url:
            redis_url = str(redis_url).strip()
        if not redis_url or redis_url.lower().startswith("memory"):
            logger.info('Using In-Memory storage (REDIS_URL=memory://)')
            return MemoryStorage()

        try:
            import redis  # type: ignore
        except Exception as e:
            logger.warning(f'Redis library not available, using memory: {e}')
            return MemoryStorage()

        try:
            max_connections = _get_setting("REDIS_MAX_CONNECTIONS", None)
            ssl_enabled = _parse_bool(_get_setting("REDIS_SSL", False))
            kwargs = {"decode_responses": True}
            if max_connections:
                try:
                    kwargs["max_connections"] = int(max_connections)
                except Exception:
                    pass
            if ssl_enabled and not str(redis_url).startswith("rediss://"):
                kwargs["ssl"] = True
            client = redis.Redis.from_url(redis_url, **kwargs)
            client.ping()
            logger.info(f'Using Redis storage: {redis_url}')
            return client
        except Exception as e:
            logger.warning(f'Redis unavailable, using memory: {e}')
            return MemoryStorage()

    def create_voice_room(
        self,
        room_id: str,
        match_id: str,
        room_data: dict,
        ttl: int = 3600
    ) -> bool:
        """Create voice room with proper data serialization."""
        try:
            logger.info(
                f'Creating memory room: room:{room_id}, match_room:{match_id}'
            )
            # Save room_data
            self.redis.hset(f'room:{room_id}', room_data)
            # Set TTL for room
            self.redis.expire(f'room:{room_id}', ttl)
            # Save match_id -> room_id relation
            self.redis.setex(f'match_room:{match_id}', ttl, room_id)
            logger.info(f'Memory room created: {room_id}')
            return True
        except Exception as e:
            logger.error(f'Failed to create voice room in memory: {e}')
            return False

    def get_voice_room(self, room_id: str) -> Dict[str, Any]:
        """Get voice room with proper deserialization."""
        try:
            room_data = self.redis.hgetall(f'room:{room_id}')
            if not room_data:
                logger.info(f'No room data found for room_id: {room_id}')
                return {}
            logger.info(f'Retrieved room data keys: {list(room_data.keys())}')
            # Deserialize fields
            result = {}
            for key, value in room_data.items():
                if key == 'players' and value:
                    try:
                        result[key] = (
                            json.loads(value) if isinstance(value, str) else value
                        )
                    except json.JSONDecodeError:
                        result[key] = value.split(',') if value else []
                elif key in ['blue_team', 'red_team'] and value:
                    try:
                        result[key] = (
                            json.loads(value) if isinstance(value, str) else value
                        )
                        logger.info(f'Successfully parsed {key}: {result[key]}')
                    except json.JSONDecodeError:
                        result[key] = value.split(',') if value else []
                        logger.warning(
                            f'Used fallback parsing for {key}: {result[key]}'
                        )
                elif key == 'discord_channels' and value:
                    try:
                        result[key] = (
                            json.loads(value) if isinstance(value, str) else value
                        )
                    except json.JSONDecodeError:
                        result[key] = {}
                elif key in ['is_active']:
                    result[key] = str(value).lower() == 'true'
                else:
                    result[key] = value
            logger.info(
                f'Final room data: blue_team={result.get("blue_team")}, '
                f'red_team={result.get("red_team")}'
            )
            return result
        except Exception as e:
            logger.error(f'Failed to get voice room: {e}')
            return {}

    def get_voice_room_by_match(self, match_id: str) -> Dict[str, Any]:
        """Get voice room by match ID."""
        try:
            room_id = self.redis.get(f'match_room:{match_id}')
            if room_id:
                return self.get_voice_room(room_id)
            return {}
        except Exception as e:
            logger.error(f'Failed to get room by match: {e}')
            return {}

    def delete_voice_room(self, match_id: str) -> bool:
        """Delete voice room by match ID."""
        try:
            room_id = self.redis.get(f'match_room:{match_id}')
            if not room_id:
                return False
            self.redis.delete(f'room:{room_id}')
            self.redis.delete(f'match_room:{match_id}')
            return True
        except Exception as e:
            logger.error(f'Failed to delete voice room: {e}')
            return False

    def get_all_active_rooms(self) -> List[Dict[str, Any]]:
        """Get all active voice rooms."""
        try:
            rooms = []
            for key in self.redis.scan_iter():
                if key.startswith('room:'):
                    room_id = key.replace('room:', '')
                    room_data = self.get_voice_room(room_id)
                    if room_data and room_data.get('is_active'):
                        rooms.append({
                            'room_id': room_id,
                            'match_id': room_data.get('match_id'),
                            'players': room_data.get('players', []),
                            'created_at': room_data.get('created_at'),
                            'is_active': room_data.get('is_active', False)
                        })
            return rooms
        except Exception as e:
            logger.error(f'Failed to get active rooms: {e}')
            return []

    def save_user_match_info(
        self,
        discord_user_id: int,
        match_info: dict,
        ttl: int = 3600
    ) -> bool:
        """Save user match information for automatic voice channel manage."""
        try:
            key = f'user_discord:{discord_user_id}'
            self.redis.hset(key, match_info)
            self.redis.expire(key, ttl)
            return True
        except Exception as e:
            logger.error(f'Failed to save user match info: {e}')
            return False

    def get_user_match_info(self, discord_user_id: int) -> Optional[dict]:
        """Get user match information."""
        try:
            key = f'user_discord:{discord_user_id}'
            data = self.redis.hgetall(key)
            return data if data else None
        except Exception as e:
            logger.error(f'Failed to get user match info: {e}')
            return None

    def fix_redis_key_types(self):
        """Mock method - does nothing for memory storage"""
        logger.info('Memory storage does not need key type fixes')
        return True


redis_manager = DatabaseManager()
if isinstance(redis_manager.redis, MemoryStorage):
    logger.info('Using In-Memory database storage')
else:
    logger.info('Using Redis database storage')
