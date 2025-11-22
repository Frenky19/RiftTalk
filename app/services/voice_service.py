import uuid
import logging
import json
from datetime import datetime, timezone, timedelta

from app.config import settings
from app.database import redis_manager
from app.services.discord_service import discord_service

logger = logging.getLogger(__name__)


class VoiceService:
    def __init__(self):
        self.redis = redis_manager
        self.discord_enabled = bool(settings.DISCORD_BOT_TOKEN)

    async def create_voice_room(self, match_id: str, players: list, team_data: dict = None) -> dict:
        """Create a new voice room for a match with improved team handling."""
        try:
            logger.info(f"🎮 Creating voice room for match {match_id}")
            logger.info(f"🎮 Received players: {players}")
            logger.info(f"🎮 Received team_data: {team_data}")
            
            # Нормализуем ID игроков к строкам
            normalized_players = [str(player) for player in players] if players else []
            
            # Нормализуем данные команд - ВАЖНО: используем данные из team_data как есть
            if team_data:
                # Берем blue_team и red_team напрямую из team_data
                blue_team_to_save = team_data.get('blue_team', [])
                red_team_to_save = team_data.get('red_team', [])
                
                # Сохраняем raw данные для отладки
                raw_teams_data = team_data.get('raw_teams_data')
                
                logger.info(f"🔄 Using direct team data - Blue: {blue_team_to_save}, Red: {red_team_to_save}")
            else:
                # Fallback: создаем демо-команды
                blue_team_to_save = normalized_players[:3] if len(normalized_players) >= 3 else normalized_players
                red_team_to_save = normalized_players[3:] if len(normalized_players) > 3 else []
                raw_teams_data = None
                logger.info(f"🎭 Using demo teams - Blue: {blue_team_to_save}, Red: {red_team_to_save}")
            
            # Убедимся, что все ID нормализованы к строкам
            blue_team_to_save = [str(player_id) for player_id in blue_team_to_save]
            red_team_to_save = [str(player_id) for player_id in red_team_to_save]
            
            logger.info(f"✅ Final normalized teams - Blue: {blue_team_to_save}, Red: {red_team_to_save}")
            
            room_id = f"voice_{match_id}_{uuid.uuid4().hex[:8]}"
            discord_channels = None
            
            # Discord интеграция
            if self.discord_enabled and not discord_service.mock_mode:
                try:
                    # Используем нормализованные данные о командах
                    discord_result = await discord_service.create_team_channels(
                        match_id, blue_team_to_save, red_team_to_save
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
                "players": json.dumps(normalized_players),
                "discord_channels": json.dumps(discord_channels) if discord_channels else "{}",
                "created_at": now.isoformat(),
                "expires_at": expires_at.isoformat(),
                "is_active": "true",
                "mock_mode": "true" if (discord_service.mock_mode if self.discord_enabled else True) else "false",
                "blue_team": json.dumps(blue_team_to_save),
                "red_team": json.dumps(red_team_to_save),
            }
            
            # Добавляем raw данные для отладки если есть
            if raw_teams_data:
                room_data["raw_teams_data"] = json.dumps(raw_teams_data)

            logger.info(f"💾 Saving to Redis: blue_team={blue_team_to_save}, red_team={red_team_to_save}")

            # Сохраняем в Redis
            success = self.redis.create_voice_room(room_id, match_id, room_data)
            if not success:
                logger.error("❌ Failed to save to Redis")
                return {"error": "Failed to create voice room"}
            
            logger.info(f"✅ Voice room created: {room_id}")
            
            # Возвращаем простой dict без discord_channels для безопасности
            return {
                "room_id": room_id,
                "match_id": match_id,
                "players": normalized_players,
                "created_at": now.isoformat(),
                "blue_team": blue_team_to_save,
                "red_team": red_team_to_save,
                "status": "success",
                "note": "Discord channels created securely. Use auto-assign to get your team's invite link."
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

    def get_voice_room_discord_channels(self, match_id: str) -> dict:
        """Get discord channels for a voice room (internal use only)."""
        try:
            room_data = self.redis.get_voice_room_by_match(match_id)
            if not room_data:
                return {}
            
            discord_channels = room_data.get('discord_channels')
            if isinstance(discord_channels, str):
                return json.loads(discord_channels)
            return discord_channels or {}
        except Exception as e:
            logger.error(f"Failed to get discord channels: {e}")
            return {}


voice_service = VoiceService()
