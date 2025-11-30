"""
Database module with automatic fallback to in-memory storage
"""

import logging
import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta
import threading

logger = logging.getLogger(__name__)


class MemoryStorage:
    """In-Memory хранилище с интерфейсом совместимым с Redis"""
    
    def __init__(self):
        self._data = {}
        self._expiry = {}
        self._lock = threading.RLock()
        logger.info("✅ In-Memory хранилище инициализировано")
    
    def ping(self):
        """Всегда возвращает True для совместимости с Redis"""
        return True
    
    def hset(self, key: str, mapping: Dict[str, Any]) -> bool:
        """Установка hash значения"""
        with self._lock:
            if key not in self._data:
                self._data[key] = {}
            
            if not isinstance(self._data[key], dict):
                self._data[key] = {}
            
            self._data[key].update(mapping)
            return True
    
    def hget(self, key: str, field: str) -> Optional[str]:
        """Получение значения из hash по полю"""
        with self._lock:
            if key in self._data and isinstance(self._data[key], dict):
                return self._data[key].get(field)
            return None
    
    def hgetall(self, key: str) -> Dict[str, Any]:
        """Получение всех полей hash"""
        with self._lock:
            if key in self._data and isinstance(self._data[key], dict):
                return self._data[key].copy()
            return {}
    
    def get(self, key: str) -> Optional[str]:
        """Получение значения по ключу"""
        with self._lock:
            # Проверяем expiry
            if key in self._expiry and datetime.now(timezone.utc) > self._expiry[key]:
                del self._data[key]
                del self._expiry[key]
                return None
            
            if key in self._data:
                if isinstance(self._data[key], (dict, list)):
                    return json.dumps(self._data[key])
                return str(self._data[key])
            return None
    
    def setex(self, key: str, time: int, value: Any) -> bool:
        """Установка значения с expiry"""
        with self._lock:
            self._data[key] = value
            if time > 0:
                self._expiry[key] = datetime.now(timezone.utc) + timedelta(seconds=time)
            return True
    
    def expire(self, key: str, time: int) -> bool:
        """Установка времени жизни для существующего ключа"""
        with self._lock:
            if key in self._data:
                if time > 0:
                    self._expiry[key] = datetime.now(timezone.utc) + timedelta(seconds=time)
                else:
                    # Если время 0 или отрицательное, удаляем expiry
                    if key in self._expiry:
                        del self._expiry[key]
                return True
            return False
    
    def delete(self, key: str) -> bool:
        """Удаление ключа"""
        with self._lock:
            if key in self._data:
                del self._data[key]
            if key in self._expiry:
                del self._expiry[key]
            return True
    
    def exists(self, key: str) -> bool:
        """Проверка существования ключа"""
        with self._lock:
            # Проверяем expiry
            if key in self._expiry and datetime.now(timezone.utc) > self._expiry[key]:
                del self._data[key]
                del self._expiry[key]
                return False
            return key in self._data
    
    def scan_iter(self, match: str = None):
        """Итерация по ключам (упрощенная версия)"""
        with self._lock:
            current_time = datetime.now(timezone.utc)
            
            # Очищаем просроченные ключи
            expired_keys = [k for k, exp in self._expiry.items() if current_time > exp]
            for key in expired_keys:
                del self._data[key]
                del self._expiry[key]
            
            # Возвращаем ключи по паттерну
            for key in list(self._data.keys()):
                if match is None or (match and match.replace('*', '') in key):
                    yield key
    
    def type(self, key: str) -> str:
        """Определение типа ключа (упрощенная версия)"""
        with self._lock:
            if key not in self._data:
                return "none"
            if isinstance(self._data[key], dict):
                return "hash"
            elif isinstance(self._data[key], list):
                return "list"
            else:
                return "string"
    
    def pipeline(self):
        """Возвращает pipeline для batch операций"""
        return MemoryPipeline(self)


class MemoryPipeline:
    """In-Memory pipeline для batch операций"""
    
    def __init__(self, storage: MemoryStorage):
        self.storage = storage
        self.commands = []
    
    def hset(self, key: str, mapping: Dict[str, Any] = None):
        """Добавляет hset команду в pipeline"""
        self.commands.append(('hset', key, mapping))
        return self
    
    def expire(self, key: str, time: int):
        """Добавляет expire команду в pipeline"""
        self.commands.append(('expire', key, time))
        return self
    
    def set(self, key: str, value: Any, ex: int = None):
        """Добавляет set команду в pipeline"""
        self.commands.append(('set', key, value, ex))
        return self
    
    def delete(self, key: str):
        """Добавляет delete команду в pipeline"""
        self.commands.append(('delete', key))
        return self
    
    def execute(self):
        """Выполняет все команды в pipeline"""
        results = []
        for command in self.commands:
            try:
                if command[0] == 'hset':
                    result = self.storage.hset(command[1], command[2])
                    results.append(result)
                elif command[0] == 'expire':
                    # Вызываем метод expire
                    result = self.storage.expire(command[1], command[2])
                    results.append(result)
                elif command[0] == 'set':
                    if command[3] is not None:
                        result = self.storage.setex(command[1], command[3], command[2])
                    else:
                        self.storage._data[command[1]] = command[2]
                        result = True
                    results.append(result)
                elif command[0] == 'delete':
                    result = self.storage.delete(command[1])
                    results.append(result)
            except Exception as e:
                logger.error(f"Pipeline command error: {e}")
                results.append(False)
        
        return results


class DatabaseManager:
    """Mock менеджер базы данных с интерфейсом совместимым с RedisManager"""
    
    def __init__(self):
        self.redis = MemoryStorage()
        logger.info("✅ Mock Database Manager инициализирован")
    
    def create_voice_room(self, room_id: str, match_id: str, room_data: dict, ttl: int = 3600) -> bool:
        """Create voice room with proper data serialization."""
        try:
            logger.info(f"💾 Creating memory room: room:{room_id}, match_room:{match_id}")
            
            # Сохраняем room_data
            self.redis.hset(f"room:{room_id}", room_data)
            
            # Устанавливаем TTL для room
            self.redis.expire(f"room:{room_id}", ttl)
            
            # Сохраняем связь match_id -> room_id
            self.redis.setex(f"match_room:{match_id}", ttl, room_id)
            
            logger.info(f"✅ Memory room created: {room_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to create voice room in memory: {e}")
            return False

    def get_voice_room(self, room_id: str) -> Dict[str, Any]:
        """Get voice room with proper deserialization."""
        try:
            room_data = self.redis.hgetall(f"room:{room_id}")
            if not room_data:
                logger.info(f"🔍 No room data found for room_id: {room_id}")
                return {}
            
            logger.info(f"📥 Retrieved room data keys: {list(room_data.keys())}")
            
            # Десериализация полей
            result = {}
            for key, value in room_data.items():
                if key == 'players' and value:
                    try:
                        result[key] = json.loads(value) if isinstance(value, str) else value
                    except json.JSONDecodeError:
                        result[key] = value.split(',') if value else []
                elif key in ['blue_team', 'red_team'] and value:
                    try:
                        result[key] = json.loads(value) if isinstance(value, str) else value
                        logger.info(f"✅ Successfully parsed {key}: {result[key]}")
                    except json.JSONDecodeError:
                        result[key] = value.split(',') if value else []
                        logger.warning(f"⚠️ Used fallback parsing for {key}: {result[key]}")
                elif key == 'discord_channels' and value:
                    try:
                        result[key] = json.loads(value) if isinstance(value, str) else value
                    except json.JSONDecodeError:
                        result[key] = {}
                elif key in ['is_active', 'mock_mode']:
                    result[key] = str(value).lower() == 'true'
                else:
                    result[key] = value
                    
            logger.info(f"✅ Final room data: blue_team={result.get('blue_team')}, red_team={result.get('red_team')}")
            return result
            
        except Exception as e:
            logger.error(f"❌ Failed to get voice room: {e}")
            return {}

    def get_voice_room_by_match(self, match_id: str) -> Dict[str, Any]:
        """Get voice room by match ID."""
        try:
            room_id = self.redis.get(f"match_room:{match_id}")
            if room_id:
                return self.get_voice_room(room_id)
            return {}
        except Exception as e:
            logger.error(f"Failed to get room by match: {e}")
            return {}

    def delete_voice_room(self, match_id: str) -> bool:
        """Delete voice room by match ID."""
        try:
            room_id = self.redis.get(f"match_room:{match_id}")
            if not room_id:
                return False
            
            self.redis.delete(f"room:{room_id}")
            self.redis.delete(f"match_room:{match_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete voice room: {e}")
            return False

    def get_all_active_rooms(self) -> List[Dict[str, Any]]:
        """Get all active voice rooms."""
        try:
            rooms = []
            for key in self.redis.scan_iter():
                if key.startswith("room:"):
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
            self.redis.hset(key, match_info)
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

    def fix_redis_key_types(self):
        """Mock method - ничего не делает для памяти"""
        logger.info("✅ Memory storage doesn't need key type fixes")
        return True


# Глобальный экземпляр
redis_manager = DatabaseManager()
logger.info("✅ Using In-Memory database storage (Redis not available)")