import redis
import json
import logging
from typing import Dict, Any
from urllib.parse import urlparse
import os

from app.utils.exceptions import DatabaseException

logger = logging.getLogger(__name__)


class RedisManager:

    def __init__(self):
        self._init_redis()

    def _init_redis(self):
        """Initialize Redis connection with proper error handling."""
        max_retries = 5
        for attempt in range(max_retries):
            try:
                # Parse Redis URL for Docker compatibility
                redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
                parsed = urlparse(redis_url)
                # Connection parameters
                connection_params = {
                    'host': parsed.hostname or 'localhost',
                    'port': parsed.port or 6379,
                    'db': int(parsed.path.lstrip('/')) if parsed.path else 0,
                    'decode_responses': True,
                    'socket_connect_timeout': 5,
                    'retry_on_timeout': True,
                    'health_check_interval': 30
                }
                # Add password if present
                if parsed.password:
                    connection_params['password'] = parsed.password
                self.redis = redis.Redis(**connection_params)
                # Test connection
                self.redis.ping()
                logger.info(
                    f"✅ Redis connected to {connection_params['host']}:{connection_params['port']}"
                )
                break
            except redis.ConnectionError as e:
                logger.warning(f"Redis connection attempt {attempt + 1}/{max_retries} failed: {e}")
                if attempt == max_retries - 1:
                    raise DatabaseException(f"Redis connection failed after {max_retries} attempts")
                import time
                time.sleep(2)
            except Exception as e:
                logger.error(f"Unexpected Redis error: {e}")
                raise DatabaseException(f"Redis initialization failed: {e}")

    def create_voice_room(self, room_id: str, match_id: str, room_data: Dict[str, Any], ttl: int = 3600) -> bool:
        """Create voice room with proper data serialization."""
        try:
            pipeline = self.redis.pipeline()
            # Serialize complex fields
            serialized_data = room_data.copy()
            if 'players' in serialized_data and isinstance(serialized_data['players'], list):
                serialized_data['players'] = ','.join(serialized_data['players'])
            if 'discord_channels' in serialized_data:
                # ⭐⭐⭐ Убедитесь, что используется json.dumps ⭐⭐⭐
                serialized_data['discord_channels'] = json.dumps(serialized_data['discord_channels'])
            pipeline.hset(f"room:{room_id}", mapping=serialized_data)
            pipeline.expire(f"room:{room_id}", ttl)
            pipeline.set(f"match_room:{match_id}", room_id, ex=ttl)
            results = pipeline.execute()
            return all(results)
        except Exception as e:
            logger.error(f"Failed to create voice room: {e}")
            return False

    def get_voice_room(self, room_id: str) -> Dict[str, Any]:
        """Get voice room with proper deserialization."""
        try:
            room_data = self.redis.hgetall(f"room:{room_id}")
            if not room_data:
                return {}
            # Deserialize fields
            if 'players' in room_data:
                room_data['players'] = room_data['players'].split(',')
            if 'discord_channels' in room_data and room_data['discord_channels']:
                try:
                    # ⭐⭐⭐ Убедитесь, что используется json.loads ⭐⭐⭐
                    room_data['discord_channels'] = json.loads(room_data['discord_channels'])
                except json.JSONDecodeError:
                    room_data['discord_channels'] = {}
            if 'is_active' in room_data:
                room_data['is_active'] = room_data['is_active'].lower() == 'true'
            if 'mock_mode' in room_data:
                room_data['mock_mode'] = room_data['mock_mode'].lower() == 'true'
            return room_data
        except Exception as e:
            logger.error(f"Failed to get voice room: {e}")
            return {}

    def get_voice_room_by_match(self, match_id: str) -> Dict[str, Any]:
        """Get voice room by match ID."""
        try:
            room_id = self.redis.get(f"match_room:{match_id}")
            return self.get_voice_room(room_id) if room_id else {}
        except Exception as e:
            logger.error(f"Failed to get room by match: {e}")
            return {}

    def delete_voice_room(self, match_id: str) -> bool:
        """Delete voice room by match ID."""
        try:
            room_id = self.redis.get(f"match_room:{match_id}")
            if not room_id:
                return False
            pipeline = self.redis.pipeline()
            pipeline.delete(f"room:{room_id}")
            pipeline.delete(f"match_room:{match_id}")
            return all(pipeline.execute())
        except Exception as e:
            logger.error(f"Failed to delete voice room: {e}")
            return False

    def get_all_active_rooms(self) -> list:
        """Get all active voice rooms."""
        try:
            rooms = []
            pattern = "room:*"
            for key in self.redis.scan_iter(match=pattern):
                room_id = key.replace("room:", "")
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
            logger.error(f"Failed to get active rooms: {e}")
            return []


redis_manager = RedisManager()
