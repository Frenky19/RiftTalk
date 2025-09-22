import redis
from redis.connection import ConnectionPool
from datetime import datetime, timezone, timedelta
from app.config import settings
from app.utils.exceptions import DatabaseException
import logging

logger = logging.getLogger(__name__)


class RedisManager:
    def __init__(self):
        try:
            # Создаем пул соединений
            self.connection_pool = ConnectionPool.from_url(
                settings.REDIS_URL,
                max_connections=settings.REDIS_MAX_CONNECTIONS,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
                health_check_interval=30
            )
            self.redis = redis.Redis(connection_pool=self.connection_pool)
            # Тестируем соединение
            self.redis.ping()
            logger.info("✅ Redis connection established successfully")
        except redis.ConnectionError as e:
            logger.error(f"❌ Redis connection failed: {e}")
            raise DatabaseException(f"Redis connection failed: {e}")
        except Exception as e:
            logger.error(
                f"❌ Unexpected error during Redis initialization: {e}"
            )
            raise DatabaseException(f"Redis initialization failed: {e}")

    def create_voice_room(
            self,
            room_id: str,
            match_id: str,
            players: list,
            ttl: int = 2700) -> bool:
        """Create a voice room with expiration"""
        try:
            room_data = {
                "room_id": room_id,
                "match_id": match_id,
                "players": ",".join(players),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "expires_at": (
                    datetime.now(timezone.utc) + timedelta(seconds=ttl)
                ).isoformat(),
                "is_active": "true"
            }
            pipeline = self.redis.pipeline()
            pipeline.hset(f"room:{room_id}", mapping=room_data)
            pipeline.expire(f"room:{room_id}", ttl)
            # Сохраняем связь match_id -> room_id для быстрого поиска
            pipeline.set(f"match_room:{match_id}", room_id, ex=ttl)
            results = pipeline.execute()
            return all(results)
        except redis.RedisError as e:
            logger.error(f"Failed to create voice room {room_id}: {e}")
            raise DatabaseException(f"Failed to create room: {e}")

    def get_voice_room_by_match(self, match_id: str) -> dict:
        """Get voice room by match ID"""
        try:
            room_id = self.redis.get(f"match_room:{match_id}")
            if not room_id:
                return {}
            return self.get_voice_room(room_id)
        except redis.RedisError as e:
            logger.error(f"Failed to get room for match {match_id}: {e}")
            return {}

    def get_voice_room(self, room_id: str) -> dict:
        """Get voice room data"""
        try:
            room_data = self.redis.hgetall(f"room:{room_id}")
            if not room_data:
                return {}
            # Преобразуем данные обратно в правильные типы
            if "players" in room_data:
                room_data["players"] = room_data["players"].split(",")
            if "is_active" in room_data:
                room_data["is_active"] = room_data["is_active"].lower() == "true"
            return room_data
        except redis.RedisError as e:
            logger.error(f"Failed to get room {room_id}: {e}")
            return {}

    def delete_voice_room(self, match_id: str) -> bool:
        """Delete a voice room by match ID"""
        try:
            room_id = self.redis.get(f"match_room:{match_id}")
            if room_id:
                pipeline = self.redis.pipeline()
                pipeline.delete(f"room:{room_id}")
                pipeline.delete(f"match_room:{match_id}")
                results = pipeline.execute()
                return all(results)
            return False
        except redis.RedisError as e:
            logger.error(f"Failed to delete room for match {match_id}: {e}")
            return False

    def is_room_active(self, room_id: str) -> bool:
        """Check if room exists and is active"""
        try:
            room_data = self.get_voice_room(room_id)
            return room_data.get("is_active", False)
        except redis.RedisError:
            return False

    def get_redis_info(self) -> dict:
        """Get Redis server information"""
        try:
            info = self.redis.info()
            return {
                "version": info.get("redis_version"),
                "used_memory": info.get("used_memory_human"),
                "connected_clients": info.get("connected_clients"),
                "keyspace_hits": info.get("keyspace_hits"),
                "keyspace_misses": info.get("keyspace_misses")
            }
        except redis.RedisError as e:
            logger.error(f"Failed to get Redis info: {e}")
            return {}


# Global Redis instance
redis_manager = RedisManager()
