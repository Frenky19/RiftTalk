import redis
import os
from dotenv import load_dotenv


load_dotenv()


class RedisManager:

    def __init__(self):
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        self.connection = redis.Redis.from_url(
            self.redis_url, decode_responses=True
        )

    def create_voice_room(
            self, match_id: str, players: list, ttl: int = 3599) -> str:
        """Создание голосовой комнаты (60 минут)"""
        room_id = f"voice_{match_id}"
        self.connection.sadd(room_id, *players)
        self.connection.expire(room_id, ttl)
        return room_id

    def get_room_players(self, match_id: str) -> list:
        """Получение игроков в комнате"""
        room_id = f"voice_{match_id}"
        return self.connection.smembers(room_id)

    def delete_room(self, match_id: str):
        """Удаление комнаты после матча"""
        room_id = f"voice_{match_id}"
        self.connection.delete(room_id)

    def is_room_active(self, match_id: str) -> bool:
        """Проверка активности комнаты"""
        return self.connection.exists(f"voice_{match_id}") == 1


if __name__ == "__main__":
    redis_mgr = RedisManager()
    room = redis_mgr.create_voice_room("match123", ["summoner1", "summoner2"])
    print(redis_mgr.get_room_players("match123"))
