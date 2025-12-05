import uuid
import logging
import json
from datetime import datetime, timezone, timedelta

from app.config import settings
from app.database import redis_manager
from app.services.discord_service import discord_service
from app.services.lcu_service import lcu_service


logger = logging.getLogger(__name__)


def safe_json_parse(data, default=None):
    """Safely parse JSON data with detailed error logging."""
    if data is None:
        return default
    if isinstance(data, (list, dict)):
        return data
    if isinstance(data, str):
        try:
            return json.loads(data)
        except json.JSONDecodeError as e:
            logger.warning(f"⚠️ Failed to parse JSON: {data}, error: {e}")
            # Попробуем разобрать как список, разделенный запятыми
            if ',' in data:
                return [item.strip() for item in data.split(',') if item.strip()]
            return default
    return default


class VoiceService:
    def __init__(self):
        self.redis = redis_manager
        self.discord_enabled = bool(settings.DISCORD_BOT_TOKEN)

    def get_active_match_id_for_summoner(self, summoner_id: str) -> str:
        """Get active match ID for a summoner."""
        try:
            # Проверяем разные ключи где мог сохраниться match_id
            match_info_key = f"user_match:{summoner_id}"
            match_info = self.redis.redis.hgetall(match_info_key)
            
            if match_info and match_info.get('match_id'):
                return match_info['match_id']
                
            # Также проверяем user ключ
            user_key = f"user:{summoner_id}"
            user_data = self.redis.redis.hgetall(user_key)
            if user_data and user_data.get('current_match'):
                return user_data['current_match']
                
            return None
        except Exception as e:
            logger.error(f"Error getting active match: {e}")
            return None

    async def create_or_get_voice_room(self, match_id: str, players: list, team_data: dict = None) -> dict:
        """Create or get existing voice room for a match with improved team handling."""
        try:
            logger.info(f"🎮 Creating or getting voice room for match {match_id}")
            
            # 🔥 КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: Проверяем, существует ли уже комната для этого матча
            existing_room = self.redis.get_voice_room_by_match(match_id)
            if existing_room and existing_room.get('is_active'):
                logger.info(f"✅ Voice room already exists for match {match_id}, returning existing room")
                
                # Добавляем текущего игрока в существующую комнату если его там нет
                current_summoner = await lcu_service.lcu_connector.get_current_summoner()
                if current_summoner:
                    summoner_id = str(current_summoner.get('summonerId'))
                    existing_players = safe_json_parse(existing_room.get('players'), [])
                    
                    if summoner_id not in existing_players:
                        existing_players.append(summoner_id)
                        # Обновляем список игроков в комнате
                        room_id = existing_room.get('room_id')
                        redis_manager.redis.hset(
                            f"room:{room_id}",
                            mapping={"players": json.dumps(existing_players)}
                        )
                        logger.info(f"✅ Added player {summoner_id} to existing room {room_id}")
                
                # Проверяем и обновляем данные команд если нужно
                if team_data and (team_data.get('blue_team') or team_data.get('red_team')):
                    room_id = existing_room.get('room_id')
                    if room_id:
                        # Обновляем данные команд
                        update_data = {}
                        if team_data.get('blue_team'):
                            update_data['blue_team'] = json.dumps(team_data['blue_team'])
                        if team_data.get('red_team'):
                            update_data['red_team'] = json.dumps(team_data['red_team'])
                        
                        if update_data:
                            self.redis.redis.hset(f"room:{room_id}", mapping=update_data)
                            logger.info(f"✅ Updated team data for existing room {room_id}")
                
                return {
                    "room_id": existing_room.get('room_id'),
                    "match_id": match_id,
                    "players": existing_room.get('players', []),
                    "created_at": existing_room.get('created_at'),
                    "blue_team": safe_json_parse(existing_room.get('blue_team'), []),
                    "red_team": safe_json_parse(existing_room.get('red_team'), []),
                    "status": "existing_room",
                    "note": "Using existing voice room for this match"
                }
            
            logger.info(f"🎮 No existing room found, creating new one for match {match_id}")
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
                    discord_result = await discord_service.create_or_get_team_channels(
                        match_id, blue_team_to_save, red_team_to_save
                    )
                    
                    if discord_result:
                        discord_channels = discord_result
                        logger.info(f"✅ Created/retrieved Discord channels for match {match_id}")
                    else:
                        logger.warning(f"⚠️ Discord channels creation/retrieval failed for match {match_id}")
                        
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
            
            # 🔥 КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: Сохраняем match_id для всех игроков
            logger.info(f"💾 Saving match info for {len(normalized_players)} players")
            for player_id in normalized_players:
                user_match_key = f"user_match:{player_id}"
                match_info = {
                    'match_id': match_id,
                    'room_id': room_id,
                    'created_at': now.isoformat()
                }
                # Сохраняем как hash для consistency
                self.redis.redis.hset(user_match_key, mapping=match_info)
                self.redis.redis.expire(user_match_key, 3600)  # 1 hour
                logger.debug(f"💾 Saved match info for player {player_id}: {match_info}")
            
            logger.info(f"✅ Voice room created: {room_id}")
            
            # Возвращаем простой dict без discord_channels для безопасности
            return {
                "room_id": room_id,
                "match_id": match_id,
                "players": normalized_players,
                "created_at": now.isoformat(),
                "blue_team": blue_team_to_save,
                "red_team": red_team_to_save,
                "status": "new_room",
                "note": "Discord channels created securely. Use auto-assign to get your team's invite link."
            }
            
        except Exception as e:
            logger.error(f"❌ Voice room creation failed: {e}")
            return {"error": str(e)}

    async def close_voice_room(self, match_id: str) -> bool:
        """Close voice room and cleanup with improved error handling."""
        try:
            logger.info(f"🧹 Closing voice room for match {match_id}")
            
            # Get room data
            room_data = self.redis.get_voice_room_by_match(match_id)
            if not room_data:
                logger.warning(f"⚠️ No room data found for match {match_id}")
                return False
                
            logger.info(f"📋 Room data found: {room_data.keys()}")
            
            # Cleanup Discord channels if they exist
            if room_data.get('discord_channels'):
                try:
                    discord_channels = room_data['discord_channels']
                    
                    # Если discord_channels это строка (JSON), парсим её
                    if isinstance(discord_channels, str):
                        try:
                            discord_channels = json.loads(discord_channels)
                            logger.info("✅ Parsed discord_channels from JSON")
                        except json.JSONDecodeError as e:
                            logger.error(f"❌ Failed to parse discord_channels JSON: {e}")
                            discord_channels = {}
                    
                    logger.info(f"🎯 Discord channels to cleanup: {discord_channels.keys()}")
                    
                    if discord_channels and isinstance(discord_channels, dict):
                        await discord_service.cleanup_match_channels(discord_channels)
                        logger.info(f"✅ Successfully cleaned up Discord channels for match {match_id}")
                    else:
                        logger.warning("⚠️ No valid discord_channels data for cleanup")
                        
                except Exception as e:
                    logger.error(f"❌ Discord cleanup error: {e}")
            
            # Delete from Redis
            delete_success = self.redis.delete_voice_room(match_id)
            if delete_success:
                logger.info(f"✅ Successfully deleted voice room from Redis for match {match_id}")
            else:
                logger.warning(f"⚠️ Failed to delete voice room from Redis for match {match_id}")
                
            return delete_success
            
        except Exception as e:
            logger.error(f"❌ Close voice room error: {e}")
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

    async def add_player_to_existing_room(self, summoner_id: str, match_id: str, team_name: str) -> bool:
        """Add a player to an existing voice room and assign to team."""
        try:
            logger.info(f"👤 Adding player {summoner_id} to existing room for match {match_id}, team: {team_name}")
            
            # Get room data
            room_data = self.redis.get_voice_room_by_match(match_id)
            if not room_data:
                logger.error(f"❌ Room not found for match {match_id}")
                return False
            
            room_id = room_data.get('room_id')
            if not room_id:
                logger.error(f"❌ Room ID not found for match {match_id}")
                return False
            
            # Add player to players list
            players = safe_json_parse(room_data.get('players'), [])
            if summoner_id not in players:
                players.append(summoner_id)
                self.redis.redis.hset(
                    f"room:{room_id}",
                    mapping={"players": json.dumps(players)}
                )
                logger.info(f"✅ Added player {summoner_id} to room {room_id}")
            
            # Update team data if needed
            blue_team = safe_json_parse(room_data.get('blue_team'), [])
            red_team = safe_json_parse(room_data.get('red_team'), [])
            
            if team_name == "Blue Team" and summoner_id not in blue_team:
                blue_team.append(summoner_id)
                self.redis.redis.hset(
                    f"room:{room_id}",
                    "blue_team",
                    json.dumps(blue_team)
                )
                logger.info(f"✅ Added player {summoner_id} to Blue Team")
            elif team_name == "Red Team" and summoner_id not in red_team:
                red_team.append(summoner_id)
                self.redis.redis.hset(
                    f"room:{room_id}",
                    "red_team",
                    json.dumps(red_team)
                )
                logger.info(f"✅ Added player {summoner_id} to Red Team")
            
            # Save match info for player
            user_match_key = f"user_match:{summoner_id}"
            match_info = {
                'match_id': match_id,
                'room_id': room_id,
                'team_name': team_name,
                'joined_at': datetime.now(timezone.utc).isoformat()
            }
            self.redis.redis.hset(user_match_key, mapping=match_info)
            self.redis.redis.expire(user_match_key, 3600)
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to add player to existing room: {e}")
            return False


# Global instance
voice_service = VoiceService()