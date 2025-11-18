import uuid
import logging
import json
from datetime import datetime, timezone, timedelta

from app.config import settings
from app.database import redis_manager
# from app.models import VoiceRoom
# from app.utils.exceptions import VoiceServiceException
from app.services.discord_service import discord_service

logger = logging.getLogger(__name__)


class VoiceService:
    def __init__(self):
        self.redis = redis_manager
        self.discord_enabled = bool(settings.DISCORD_BOT_TOKEN)

    async def create_voice_room(self, match_id: str, players: list, team_data: dict = None) -> dict:
        """Create a new voice room for a match."""
        try:
            logger.info(f"🎮 Creating voice room for match {match_id}")
            
            # Валидация и преобразование players
            if not players:
                players = ["player1", "player2", "player3", "player4", "player5"]
                logger.warning(f"Using default players for match {match_id}")
            
            # Убедимся, что players - это список строк
            if isinstance(players, str):
                players = [players]
            elif hasattr(players, '__iter__') and not isinstance(players, (list, tuple)):
                players = list(players)
            
            room_id = f"voice_{match_id}_{uuid.uuid4().hex[:8]}"
            discord_channels = None
            
            # Discord интеграция
            if self.discord_enabled and not discord_service.mock_mode:
                try:
                    blue_team = team_data.get('blue_team', []) if team_data else players[:3]
                    red_team = team_data.get('red_team', []) if team_data else players[3:]
                    
                    discord_result = await discord_service.create_team_channels(
                        match_id, blue_team, red_team
                    )
                    
                    if discord_result:
                        discord_channels = discord_result
                        logger.info(f"✅ Created Discord channels for match {match_id}")
                    else:
                        logger.warning(f"⚠️ Discord channels creation failed for match {match_id}")
                        
                except Exception as e:
                    logger.error(f"❌ Discord error: {e}")
                    discord_channels = None
            else:
                logger.info("🔶 Discord disabled or in mock mode")

            # Подготовка данных
            now = datetime.now(timezone.utc)
            expires_at = now + timedelta(hours=1)
            
            room_data = {
                "room_id": room_id,
                "match_id": match_id,
                "players": json.dumps(players),
                "discord_channels": json.dumps(discord_channels) if discord_channels else "{}",
                "created_at": now.isoformat(),
                "expires_at": expires_at.isoformat(),
                "is_active": "true",
                "mock_mode": "true" if (discord_service.mock_mode if self.discord_enabled else True) else "false"
            }

            # Сохраняем данные о командах
            if team_data:
                room_data["blue_team"] = json.dumps(team_data.get('blue_team', []))
                room_data["red_team"] = json.dumps(team_data.get('red_team', []))
            else:
                # Демо-данные по умолчанию
                room_data["blue_team"] = json.dumps(players[:3])
                room_data["red_team"] = json.dumps(players[3:])

            # Сохраняем в Redis
            success = self.redis.create_voice_room(room_id, match_id, room_data)
            if not success:
                logger.error("❌ Failed to save to Redis")
                return {"error": "Failed to create voice room"}
            
            logger.info(f"✅ Voice room created: {room_id}")
            
            # Возвращаем простой dict вместо VoiceRoom для избежания проблем с Pydantic
            return {
                "room_id": room_id,
                "match_id": match_id,
                "players": players,
                "discord_channels": discord_channels,
                "created_at": now.isoformat(),
                "blue_team": team_data.get('blue_team', []) if team_data else players[:3],
                "red_team": team_data.get('red_team', []) if team_data else players[3:],
                "status": "success"
            }
            
        except Exception as e:
            logger.error(f"❌ Voice room creation failed: {e}")
            return {"error": str(e)}

    async def close_voice_room(self, match_id: str) -> bool:
        """Close voice room and cleanup."""
        try:
            room_data = self.redis.get_voice_room_by_match(match_id)
            if room_data and room_data.get('discord_channels'):
                try:
                    await discord_service.cleanup_match_channels(room_data['discord_channels'])
                except Exception as e:
                    logger.error(f"Discord cleanup error: {e}")
            
            return self.redis.delete_voice_room(match_id)
        except Exception as e:
            logger.error(f"Close voice room error: {e}")
            return False


voice_service = VoiceService()
