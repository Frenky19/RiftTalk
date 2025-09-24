import uuid
import logging
from datetime import datetime, timezone, timedelta
from app.config import settings
from app.database import redis_manager
from app.models import VoiceRoom
from app.utils.exceptions import VoiceServiceException
from app.services.discord_service import discord_service

logger = logging.getLogger(__name__)

class VoiceService:
    def __init__(self):
        self.redis = redis_manager
        self.discord_enabled = bool(settings.DISCORD_BOT_TOKEN)

    async def create_voice_room(self, match_id: str, players: list, team_data: dict = None) -> VoiceRoom:
        """Create a new voice room for a match with Discord integration"""
        room_id = f"voice_{match_id}_{uuid.uuid4().hex[:8]}"
        
        discord_channels = None
        if self.discord_enabled and team_data:
            try:
                discord_channels = await discord_service.create_team_channels(
                    match_id, 
                    team_data.get('blue_team', []),
                    team_data.get('red_team', [])
                )
                logger.info(f"Created Discord channels for match {match_id}")
            except Exception as e:
                logger.error(f"Failed to create Discord channels: {e}")
                # Продолжаем без Discord, не прерываем создание комнаты

        # Save to Redis
        room_data = {
            "room_id": room_id,
            "match_id": match_id,
            "players": players,
            "discord_channels": discord_channels,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=2700)).isoformat(),
            "is_active": True
        }
        
        if not self.redis.create_voice_room(room_id, match_id, room_data):
            raise VoiceServiceException("Failed to create voice room")
        
        return VoiceRoom(
            room_id=room_id,
            match_id=match_id,
            players=players,
            discord_channels=discord_channels,
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=2700)
        )

    async def close_voice_room(self, match_id: str) -> bool:
        """Close voice room and cleanup Discord channels"""
        try:
            # Get room data
            room_data = self.redis.get_voice_room_by_match(match_id)
            if room_data and room_data.get('discord_channels'):
                await discord_service.cleanup_match_channels(room_data['discord_channels'])
            
            # Delete from Redis
            return self.redis.delete_voice_room(match_id)
        except Exception as e:
            raise VoiceServiceException(f"Failed to close voice room: {e}")

    def validate_player_access(self, room_id: str, summoner_id: str) -> bool:
        """Check if a player has access to a voice room"""
        room_data = self.redis.get_voice_room(room_id)
        if not room_data or not room_data.get("is_active"):
            return False
        return summoner_id in room_data.get("players", [])

voice_service = VoiceService()
