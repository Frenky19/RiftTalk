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
        self.fix_redis_key_types()  # Автоматически исправляем ключи при инициализации

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

    def fix_redis_key_types(self):
        """Fix Redis keys that were saved with wrong types."""
        try:
            logger.info("🔧 Checking for Redis key type issues...")
            fixed_count = 0
            
            # Паттерны для поиска проблемных ключей
            patterns = ["user:*", "user_discord:*", "user_match:*"]
            
            for pattern in patterns:
                for key in self.redis.scan_iter(match=pattern):
                    try:
                        # Пробуем прочитать как hash
                        data = self.redis.hgetall(key)
                        if data:
                            continue  # Ключ в правильном формате
                        
                        # Если не hash, пробуем прочитать как string
                        str_data = self.redis.get(key)
                        if str_data:
                            logger.warning(f"⚠️ Fixing key type for {key}")
                            try:
                                # Парсим JSON и конвертируем в hash
                                parsed_data = json.loads(str_data)
                                if isinstance(parsed_data, dict):
                                    self.redis.delete(key)  # Удаляем старый ключ
                                    self.redis.hset(key, mapping=parsed_data)
                                    fixed_count += 1
                                    logger.info(f"✅ Fixed key {key} from string to hash")
                            except json.JSONDecodeError:
                                # Если не JSON, создаем простой hash
                                self.redis.delete(key)
                                self.redis.hset(key, "data", str_data)
                                fixed_count += 1
                                logger.info(f"✅ Fixed key {key} from string to hash with single field")
                                
                    except redis.exceptions.ResponseError as e:
                        if "WRONGTYPE" in str(e):
                            logger.warning(f"🔄 Converting key {key} from wrong type...")
                            # Получаем данные любым способом
                            try:
                                raw_data = self.redis.get(key)
                                if raw_data:
                                    self.redis.delete(key)
                                    self.redis.hset(key, "value", raw_data)
                                    fixed_count += 1
                                    logger.info(f"✅ Converted key {key} to hash")
                            except:
                                try:
                                    # Другой тип? Пробуем получить как список
                                    raw_data = self.redis.lrange(key, 0, -1)
                                    if raw_data:
                                        self.redis.delete(key)
                                        self.redis.hset(key, "items", json.dumps(raw_data))
                                        fixed_count += 1
                                        logger.info(f"✅ Converted key {key} from list to hash")
                                except:
                                    logger.error(f"❌ Cannot convert key {key} - unknown type")
                    
            if fixed_count > 0:
                logger.info(f"✅ Fixed {fixed_count} Redis keys with type issues")
            else:
                logger.info("✅ No Redis key type issues found")
                
        except Exception as e:
            logger.error(f"❌ Error fixing Redis key types: {e}")

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
            # Используем hset для правильного формата
            self.redis.hset(key, mapping={
                "match_id": match_info.get('match_id', ''),
                "team_name": match_info.get('team_name', ''),
                "assigned_at": match_info.get('assigned_at', '')
            })
            self.redis.expire(key, ttl)
            return True
        except Exception as e:
            logger.error(f"Failed to save user match info: {e}")
            return False

    def get_user_match_info(self, discord_user_id: int) -> Optional[dict]:
        """Get user match information."""
        try:
            key = f"user_discord:{discord_user_id}"
            data = self.redis.hgetall(key)
            return data if data else None
        except Exception as e:
            logger.error(f"Failed to get user match info: {e}")
            return None


redis_manager = RedisManager()