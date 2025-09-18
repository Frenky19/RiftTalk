from datetime import datetime, timezone, timedelta
import redis
from redis.commands.json.path import Path
from app.config import settings
from app.utils.exceptions import DatabaseException
import json


class RedisManager:
    def __init__(self):
        try:
            self.redis = redis.Redis.from_url(
                settings.REDIS_URL,
                password=settings.REDIS_PASSWORD or None,
                decode_responses=True
            )
            self.redis.ping()
        except redis.ConnectionError as e:
            raise DatabaseException(f"Redis connection failed: {e}")

    def create_voice_room(self, room_id: str, match_id: str, players: list, ttl: int = 2700) -> bool:
        """Create a voice room with expiration"""
        room_data = {
            "room_id": room_id,
            "match_id": match_id,
            "players": ",".join(players),  # Сохраняем как строку
            "created_at": str(datetime.now(timezone.utc)),
            "expires_at": str(
                datetime.now(timezone.utc) + timedelta(seconds=ttl)
            ),
            "is_active": "True"
        }
        try:
            self.redis.hset(f"room:{room_id}", mapping=room_data)
            self.redis.expire(f"room:{room_id}", ttl)
            return True
        except redis.RedisError as e:
            raise DatabaseException(f"Failed to create room: {e}")

    def get_voice_room(self, room_id: str) -> dict:
        """Get voice room data"""
        try:
            room_data = self.redis.hgetall(f"room:{room_id}")
            if room_data and "players" in room_data:
                room_data["players"] = room_data["players"].split(",")
            return room_data if room_data else {}
        except redis.RedisError as e:
            raise DatabaseException(f"Failed to get room: {e}")

    def delete_voice_room(self, room_id: str) -> bool:
        """Delete a voice room"""
        try:
            return bool(self.redis.delete(f"room:{room_id}"))
        except redis.RedisError as e:
            raise DatabaseException(f"Failed to delete room: {e}")

    def is_room_active(self, room_id: str) -> bool:
        """Check if room exists and is active"""
        try:
            room_data = self.get_voice_room(room_id)
            return room_data.get("is_active", False) if room_data else False
        except redis.RedisError:
            return False

    def get_all_active_rooms(self) -> list:
        """Get all active rooms (for monitoring)"""
        try:
            rooms = []
            for key in self.redis.scan_iter("room:*"):
                room_data = self.get_voice_room(key.split(":")[1])
                if room_data and room_data.get("is_active"):
                    rooms.append(room_data)
            return rooms
        except redis.RedisError as e:
            raise DatabaseException(f"Failed to get active rooms: {e}")


# Global Redis instance
redis_manager = RedisManager()
