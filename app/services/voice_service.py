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
        """Create a new voice room for a match."""
        try:
            logger.info(f"🎮 Creating voice room for match {match_id}")
            logger.info(f"🎮 Received players: {players}")
            logger.info(f"🎮 Received team_data: {team_data}")
            
            # Валидация и преобразование players
            if not players:
                players = ["test_player", "player2", "player3", "player4", "player5"]  # ← ИЗМЕНИЛИ ЗДЕСЬ!
                logger.warning(f"Using default players for match {match_id}")
            else:
                logger.info(f"🎮 Using provided players: {players}")
            
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
                    # Используем переданные данные о командах или создаем на основе players
                    if team_data:
                        blue_team = team_data.get('blue_team', [])
                        red_team = team_data.get('red_team', [])
                        logger.info(f"🎮 Using provided teams: blue={blue_team}, red={red_team}")
                    else:
                        # Если team_data не предоставлен, создаем демо-команды
                        blue_team = players[:3]
                        red_team = players[3:]
                        logger.info(f"🎮 Created demo teams: blue={blue_team}, red={red_team}")
                    
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
            
            # Определяем команды для сохранения в Redis
            if team_data:
                blue_team_to_save = team_data.get('blue_team', [])
                red_team_to_save = team_data.get('red_team', [])
            else:
                blue_team_to_save = players[:3]
                red_team_to_save = players[3:]
            
            # Гарантируем, что test_player всегда в blue_team для демо
            if 'test_player' in players and 'test_player' not in blue_team_to_save:
                logger.info("🔄 Ensuring test_player is in blue_team for demo")
                if blue_team_to_save:
                    blue_team_to_save[0] = 'test_player'
                else:
                    blue_team_to_save = ['test_player'] + players[1:3] if len(players) > 1 else ['test_player']
            
            room_data = {
                "room_id": room_id,
                "match_id": match_id,
                "players": json.dumps(players),
                "discord_channels": json.dumps(discord_channels) if discord_channels else "{}",
                "created_at": now.isoformat(),
                "expires_at": expires_at.isoformat(),
                "is_active": "true",
                "mock_mode": "true" if (discord_service.mock_mode if self.discord_enabled else True) else "false",
                "blue_team": json.dumps(blue_team_to_save),  # ← Сохраняем исправленные команды
                "red_team": json.dumps(red_team_to_save)     # ← Сохраняем исправленные команды
            }

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
                "players": players,
                "created_at": now.isoformat(),
                "blue_team": blue_team_to_save,  # ← Возвращаем исправленные команды
                "red_team": red_team_to_save,    # ← Возвращаем исправленные команды
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
