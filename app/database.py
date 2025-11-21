import redis
import json
import logging
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse
import os

from app.utils.exceptions import DatabaseException

logger = logging.getLogger(__name__)


class RedisManager:

    def __init__(self):
        self._init_redis()

    def _init_redis(self):
        """Initialize Redis connection for local Windows setup."""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Для локального запуска используем localhost
                redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
                parsed = urlparse(redis_url)
                
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
                logger.info(f"✅ Redis connected to {connection_params['host']}:{connection_params['port']}")
                break
                
            except redis.ConnectionError as e:
                logger.warning(f"Redis connection attempt {attempt + 1}/{max_retries} failed: {e}")
                if attempt == max_retries - 1:
                    raise DatabaseException(f"Redis connection failed after {max_retries} attempts - make sure Redis is running on localhost:6379")
                import time
                time.sleep(2)
            except Exception as e:
                logger.error(f"Unexpected Redis error: {e}")
                raise DatabaseException(f"Redis initialization failed: {e}")

    def create_voice_room(self, room_id: str, match_id: str, room_data: dict, ttl: int = 3600) -> bool:
        """Create voice room with proper data serialization."""
        try:
            pipeline = self.redis.pipeline()
            
            # Простая проверка - если room_data не dict, преобразуем
            if not hasattr(room_data, 'items'):
                logger.error(f"room_data is not a dict: {type(room_data)}")
                return False
                
            pipeline.hset(f"room:{room_id}", mapping=room_data)
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
            
            # Десериализация полей
            result = {}
            for key, value in room_data.items():
                if key == 'players' and value:
                    try:
                        result[key] = json.loads(value)
                    except json.JSONDecodeError:
                        result[key] = value.split(',') if value else []
                elif key in ['blue_team', 'red_team'] and value:
                    try:
                        result[key] = json.loads(value)
                    except json.JSONDecodeError:
                        result[key] = value.split(',') if value else []
                elif key == 'discord_channels' and value:
                    try:
                        result[key] = json.loads(value)
                    except json.JSONDecodeError:
                        result[key] = {}
                elif key in ['is_active', 'mock_mode']:
                    result[key] = value.lower() == 'true'
                else:
                    result[key] = value
                    
            return result
            
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

    def get_all_active_rooms(self) -> List[Dict[str, Any]]:
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

    def save_user_match_info(self, discord_user_id: int, match_info: dict, ttl: int = 3600) -> bool:
        """Save user match information for automatic voice channel management."""
        try:
            key = f"user_discord:{discord_user_id}"
            self.redis.setex(key, ttl, json.dumps(match_info))
            return True
        except Exception as e:
            logger.error(f"Failed to save user match info: {e}")
            return False

    def get_user_match_info(self, discord_user_id: int) -> Optional[dict]:
        """Get user match information."""
        try:
            key = f"user_discord:{discord_user_id}"
            data = self.redis.get(key)
            return json.loads(data) if data else None
        except Exception as e:
            logger.error(f"Failed to get user match info: {e}")
            return None


redis_manager = RedisManager()
