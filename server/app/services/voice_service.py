import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

from app.config import settings
from app.constants import USER_MATCH_TTL_SECONDS
from app.database import redis_manager
from app.services.discord_service import discord_service

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
            logger.warning(f'Failed to parse JSON: {data}, error: {e}')
            # Try to parse as comma-separated list
            if ',' in data:
                return [
                    item.strip()
                    for item in data.split(',')
                    if item.strip()
                ]
            return default
    return default


class VoiceService:
    def __init__(self):
        self.redis = redis_manager
        self.discord_enabled = bool(settings.discord_enabled)

    @staticmethod
    def safe_json_parse(data, default=None):
        """Backward-compatible helper used by endpoints."""
        return safe_json_parse(data, default)

    async def get_active_match_id_for_summoner(
        self, summoner_id: str
    ) -> str | None:
        """Get active match ID for a summoner."""
        try:
            # Check different keys where match_id might be stored
            match_info_key = f'user_match:{summoner_id}'
            match_info = await self.redis.redis.hgetall(match_info_key)
            if match_info and match_info.get('match_id'):
                return match_info['match_id']
            # Also check user key
            user_key = f'user:{summoner_id}'
            user_data = await self.redis.redis.hgetall(user_key)
            if user_data and user_data.get('current_match'):
                return user_data['current_match']
            return None
        except Exception as e:
            logger.error(f'Error getting active match: {e}')
            return None

    async def create_or_get_voice_room(
        self,
        match_id: str,
        players: list,
        team_data: dict = None
    ) -> dict:
        """Create or get existing voice room for a match."""
        try:
            logger.info(
                f'Creating or getting voice room for match {match_id}'
            )
            #  Check if room already exists for this match
            existing_room = await self.redis.get_voice_room_by_match(match_id)
            if existing_room and existing_room.get('is_active'):
                logger.info(
                    f'Voice room already exists for match {match_id}, '
                    f'returning existing room'
                )
                # Server does not have local LCU; rely on payload players.
                # Check and update team data if needed
                if team_data and (
                    team_data.get('blue_team') or team_data.get('red_team')
                ):
                    room_id = existing_room.get('room_id')
                    if room_id:
                        # Update team data safely (do not flip existing assignments)
                        update_data = {}
                        existing_blue = safe_json_parse(
                            existing_room.get('blue_team'), []
                        ) or []
                        existing_red = safe_json_parse(
                            existing_room.get('red_team'), []
                        ) or []
                        existing_blue = [str(x) for x in existing_blue]
                        existing_red = [str(x) for x in existing_red]
                        incoming_blue = [
                            str(x) for x in (team_data.get('blue_team') or [])
                        ]
                        incoming_red = [
                            str(x) for x in (team_data.get('red_team') or [])
                        ]

                        blue_set = set(existing_blue)
                        red_set = set(existing_red)
                        for pid in incoming_blue:
                            if pid in red_set:
                                continue
                            if pid not in blue_set:
                                blue_set.add(pid)
                        for pid in incoming_red:
                            if pid in blue_set:
                                continue
                            if pid not in red_set:
                                red_set.add(pid)

                        if blue_set != set(existing_blue):
                            update_data['blue_team'] = json.dumps(sorted(blue_set))
                        if red_set != set(existing_red):
                            update_data['red_team'] = json.dumps(sorted(red_set))
                        if update_data:
                            await self.redis.redis.hset(
                                f'room:{room_id}',
                                mapping=update_data
                            )
                            logger.info(
                                f'Updated team data for existing room {room_id}'
                            )
                return {
                    'room_id': existing_room.get('room_id'),
                    'match_id': match_id,
                    'players': existing_room.get('players', []),
                    'created_at': existing_room.get('created_at'),
                    'blue_team': safe_json_parse(
                        existing_room.get('blue_team'), []
                    ),
                    'red_team': safe_json_parse(
                        existing_room.get('red_team'), []
                    ),
                    'status': 'existing_room',
                    'note': 'Using existing voice room for this match'
                }
            logger.info(
                f'No existing room found, creating new one for match {match_id}'
            )
            logger.info(f'Received players: {players}')
            logger.info(f'Received team_data: {team_data}')
            # Normalize player IDs to strings
            normalized_players = (
                [str(player) for player in players] if players else []
            )
            # Normalize team data - IMPORTANT: use team_data as is
            if team_data:
                # Take blue_team and red_team directly from team_data
                blue_team_to_save = team_data.get('blue_team', [])
                red_team_to_save = team_data.get('red_team', [])
                # Save raw data for debugging
                raw_teams_data = team_data.get('raw_teams_data')
                logger.info(
                    f'Using direct team data - Blue: {blue_team_to_save}, '
                    f'Red: {red_team_to_save}'
                )
                if not blue_team_to_save and not red_team_to_save:
                    logger.error('Team lists are empty. '
                                 'Strict mode: refusing to create a room.')
                    return {'error': 'Team lists empty'}
            else:
                logger.error(
                    'Team data is missing. Strict mode: '
                    'cannot create a room without real blue_team/red_team.'
                )
                return {'error': 'Team data missing from LCU'}
            # Ensure all IDs are normalized to strings
            blue_team_to_save = [
                str(player_id) for player_id in blue_team_to_save
            ]
            red_team_to_save = [
                str(player_id) for player_id in red_team_to_save
            ]
            logger.info(
                f'Final normalized teams - Blue: {blue_team_to_save}, '
                f'Red: {red_team_to_save}'
            )
            room_id = f'voice_{match_id}_{uuid.uuid4().hex[:8]}'
            discord_channels = None
            # Discord integration
            if self.discord_enabled:
                try:
                    discord_channels = await discord_service.create_or_get_team_channels(
                        match_id,
                        blue_team_to_save,
                        red_team_to_save,
                    )
                    logger.info(f'Created/retrieved Discord channels for match {match_id}')
                except Exception as e:
                    logger.error(f'Discord error (strict): {e}')
                    return {'error': f'Discord error: {e}'}
            # Prepare data
            now = datetime.now(timezone.utc)
            expires_at = now + timedelta(hours=1)
            room_data = {
                'room_id': room_id,
                'match_id': match_id,
                'players': json.dumps(normalized_players),
                'discord_channels': (
                    json.dumps(discord_channels) if discord_channels else '{}'
                ),
                'created_at': now.isoformat(),
                'expires_at': expires_at.isoformat(),
                'is_active': 'true',
                'blue_team': json.dumps(blue_team_to_save),
                'red_team': json.dumps(red_team_to_save),
            }
            # Add raw data for debugging if available
            if raw_teams_data:
                room_data['raw_teams_data'] = json.dumps(raw_teams_data)
            logger.info(
                f'Saving to Redis: blue_team={blue_team_to_save}, '
                f'red_team={red_team_to_save}'
            )
            # Save to Redis
            success = await self.redis.create_voice_room(
                room_id,
                match_id,
                room_data
            )
            if not success:
                logger.error('Failed to save to Redis')
                return {'error': 'Failed to create voice room'}
            # Save match_id for all players
            logger.info(
                f'Saving match info for {len(normalized_players)} players'
            )
            for player_id in normalized_players:
                user_match_key = f'user_match:{player_id}'
                match_info = {
                    'match_id': match_id,
                    'room_id': room_id,
                    'created_at': now.isoformat()
                }
                # Save as hash for consistency
                await self.redis.redis.hset(user_match_key, mapping=match_info)
                await self.redis.redis.expire(
                    user_match_key,
                    USER_MATCH_TTL_SECONDS,
                )
                logger.debug(
                    f'Saved match info for player {player_id}: {match_info}'
                )
            logger.info(f'Voice room created: {room_id}')
            # Return simple dict without discord_channels for security
            return {
                'room_id': room_id,
                'match_id': match_id,
                'players': normalized_players,
                'created_at': now.isoformat(),
                'blue_team': blue_team_to_save,
                'red_team': red_team_to_save,
                'status': 'new_room',
                'note': (
                    'Discord channels created securely. '
                    "Use auto-assign to get your team's invite link."
                )
            }
        except Exception as e:
            logger.error(f'Voice room creation failed: {e}')
            return {'error': str(e)}

    async def close_voice_room(self, match_id: str) -> bool:
        """Close voice room and cleanup with improved error handling."""
        try:
            logger.info(f'Closing voice room for match {match_id}')
            # Get room data
            room_data = await self.redis.get_voice_room_by_match(match_id)
            if not room_data:
                logger.warning(f'No room data found for match {match_id}')
                return False
            logger.info(f'Room data found: {room_data.keys()}')
            # Cleanup Discord channels/roles (idempotent)
            if self.discord_enabled:
                try:
                    await discord_service.cleanup_match_channels(
                        {'match_id': match_id}
                    )
                    logger.info(
                        f'Successfully cleaned up Discord channels/roles for '
                        f'match {match_id}'
                    )
                except Exception as e:
                    logger.error(f'Discord cleanup error: {e}')
            # Delete from Redis
            delete_success = await self.redis.delete_voice_room(match_id)
            if delete_success:
                logger.info(
                    f'Successfully deleted voice room from Redis for '
                    f'match {match_id}'
                )
            else:
                logger.warning(
                    f'Failed to delete voice room from Redis for '
                    f'match {match_id}'
                )
            return delete_success
        except Exception as e:
            logger.error(f'Close voice room error: {e}')
            return False

    async def get_voice_room_discord_channels(self, match_id: str) -> dict:
        """Get discord channels for a voice room (internal use only)."""
        try:
            room_data = await self.redis.get_voice_room_by_match(match_id)
            if not room_data:
                return {}
            discord_channels = room_data.get('discord_channels')
            if isinstance(discord_channels, str):
                return json.loads(discord_channels)
            return discord_channels or {}
        except Exception as e:
            logger.error(f'Failed to get discord channels: {e}')
            return {}

    async def handle_player_left_match(
        self,
        match_id: str,
        summoner_id: str,
        discord_user_id: int
    ) -> bool:
        """Handle a single player leaving the match early.

        - Removes the player's team role and disconnects them from match voice.
        - Does NOT delete channels/roles unless no members remain in match roles.
        """
        try:
            logger.info(
                f'Handling player leave: summoner={summoner_id}, match={match_id}'
            )
            room_data = await self.redis.get_voice_room_by_match(match_id)
            if not room_data:
                logger.warning(f'No room found for match {match_id}')
                return False

            room_id = room_data.get('room_id')
            # Mark room as a cleanup candidate (handles early leave / crashes)
            try:
                if room_id:
                    now = datetime.now(timezone.utc)
                    update = {'closing_requested_at': now.isoformat(),
                              'closing_reason': 'early_leave'}
                    try:
                        old_exp = room_data.get('expires_at')
                        if old_exp:
                            old_dt = datetime.fromisoformat(old_exp.replace('Z', '+00:00'))
                            new_dt = min(old_dt, now + timedelta(minutes=15))
                        else:
                            new_dt = now + timedelta(minutes=15)
                        update['expires_at'] = new_dt.isoformat()
                    except Exception:
                        update['expires_at'] = (now + timedelta(minutes=15)).isoformat()
                    await self.redis.redis.hset(f'room:{room_id}', mapping=update)
            except Exception as e:
                logger.debug(f'Failed to mark room for cleanup: {e}')

            # Determine team from stored room data
            blue_team = self.safe_json_parse(room_data.get('blue_team'), []) or []
            red_team = self.safe_json_parse(room_data.get('red_team'), []) or []
            team_name = None
            if summoner_id in blue_team:
                team_name = 'Blue Team'
            elif summoner_id in red_team:
                team_name = 'Red Team'

            # Prevent auto-move back: clear match tracking keys for this user
            try:
                await self.redis.redis.delete(f'user_discord:{discord_user_id}')
            except Exception:
                pass
            try:
                await self.redis.redis.delete(f'user_match:{summoner_id}')
            except Exception:
                pass
            try:
                await self.redis.redis.hdel(f'user:{summoner_id}', 'current_match')
            except Exception:
                pass

            if self.discord_enabled:
                await discord_service.remove_player_from_match(
                    discord_user_id=discord_user_id,
                    match_id=match_id,
                    team_name=team_name,
                )

            # Update players list in room (best-effort)
            try:
                room_id = room_data.get('room_id')
                if room_id:
                    players = self.safe_json_parse(room_data.get('players'), []) or []
                    players = [p for p in players if str(p) != str(summoner_id)]
                    await self.redis.redis.hset(
                        f'room:{room_id}',
                        mapping={'players': json.dumps(players)}
                    )
            except Exception as e:
                logger.warning(f'Failed to update room players list: {e}')

            # If nobody left with roles, cleanup everything
            if self.discord_enabled:
                try:
                    has_active = await discord_service.match_has_active_players(match_id)
                    if not has_active:
                        logger.info(
                            f'No active players remain for match {match_id}; closing room'
                        )
                        await self.close_voice_room(match_id)
                except Exception as e:
                    logger.error(f'Active player check failed: {e}')

            return True
        except Exception as e:
            logger.error(f'handle_player_left_match error: {e}')
            return False

    async def add_player_to_existing_room(
        self,
        summoner_id: str,
        match_id: str,
        team_name: str
    ) -> bool:
        """Add a player to an existing voice room and assign to team."""
        try:
            logger.info(
                f'Adding player {summoner_id} to existing room for match '
                f'{match_id}, team: {team_name}'
            )
            # Get room data
            room_data = await self.redis.get_voice_room_by_match(match_id)
            if not room_data:
                logger.error(f'Room not found for match {match_id}')
                return False
            room_id = room_data.get('room_id')
            if not room_id:
                logger.error(f'Room ID not found for match {match_id}')
                return False
            # Add player to players list
            players = safe_json_parse(room_data.get('players'), [])
            if summoner_id not in players:
                players.append(summoner_id)
                await self.redis.redis.hset(
                    f'room:{room_id}',
                    mapping={'players': json.dumps(players)}
                )
                logger.info(
                    f'Added player {summoner_id} to room {room_id}'
                )
            # Update team data if needed
            blue_team = safe_json_parse(room_data.get('blue_team'), [])
            red_team = safe_json_parse(room_data.get('red_team'), [])
            if team_name == 'Blue Team' and summoner_id not in blue_team:
                blue_team.append(summoner_id)
                await self.redis.redis.hset(
                    f'room:{room_id}',
                    'blue_team',
                    json.dumps(blue_team)
                )
                logger.info(
                    f'Added player {summoner_id} to Blue Team'
                )
            elif team_name == 'Red Team' and summoner_id not in red_team:
                red_team.append(summoner_id)
                await self.redis.redis.hset(
                    f'room:{room_id}',
                    'red_team',
                    json.dumps(red_team)
                )
                logger.info(
                    f'Added player {summoner_id} to Red Team'
                )
            # Save match info for player
            user_match_key = f'user_match:{summoner_id}'
            match_info = {
                'match_id': match_id,
                'room_id': room_id,
                'team_name': team_name,
                'joined_at': datetime.now(timezone.utc).isoformat()
            }
            await self.redis.redis.hset(user_match_key, mapping=match_info)
            await self.redis.redis.expire(
                user_match_key,
                USER_MATCH_TTL_SECONDS,
            )
            return True
        except Exception as e:
            logger.error(f'Failed to add player to existing room: {e}')
            return False


voice_service = VoiceService()
