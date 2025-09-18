import uuid
from datetime import datetime, timezone, timedelta
from app.config import settings
from app.database import redis_manager
from app.models import VoiceRoom, WebRTCConfig
from app.utils.exceptions import VoiceServiceException


class VoiceService:
    def __init__(self):
        self.redis = redis_manager

    def create_voice_room(self, match_id: str, players: list) -> VoiceRoom:
        """Create a new voice room for a match"""
        room_id = f"voice_{match_id}_{uuid.uuid4().hex[:8]}"
        if not self.redis.create_voice_room(room_id, match_id, players):
            raise VoiceServiceException("Failed to create voice room")
        webrtc_config = WebRTCConfig(
            ice_servers=[
                {
                    "urls": [
                        "stun:stun.l.google.com:19302",
                        "stun:stun1.l.google.com:19302"
                    ]
                }
            ],
            room_id=room_id
        )
        # Add TURN server if configured
        if settings.TURN_SERVER_URL:
            webrtc_config.ice_servers.append({
                "urls": settings.TURN_SERVER_URL,
                "username": settings.TURN_SERVER_USERNAME,
                "credential": settings.TURN_SERVER_PASSWORD
            })
        return VoiceRoom(
            room_id=room_id,
            match_id=match_id,
            players=players,
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=2700),
            webrtc_config=webrtc_config.dict()
        )

    def close_voice_room(self, match_id: str) -> bool:
        """Close all voice rooms for a match"""
        try:
            # Find all rooms for this match
            rooms = self.redis.get_all_active_rooms()
            match_rooms = [
                room for room in rooms if room["match_id"] == match_id
            ]
            # Close each room
            for room in match_rooms:
                self.redis.delete_voice_room(room["room_id"])
            return True
        except Exception as e:
            raise VoiceServiceException(f"Failed to close voice rooms: {e}")

    def validate_player_access(self, room_id: str, summoner_id: str) -> bool:
        """Check if a player has access to a voice room"""
        room_data = self.redis.get_voice_room(room_id)
        if not room_data or not room_data.get("is_active"):
            return False
        return summoner_id in room_data.get("players", [])


voice_service = VoiceService()
