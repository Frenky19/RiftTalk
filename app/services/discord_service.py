import asyncio
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import discord
from discord import CategoryChannel, Guild, Role, VoiceChannel

from app.config import settings

logger = logging.getLogger(__name__)

try:
    from app.database import redis_manager
except Exception as e:
    # Fallback when Redis is not available
    logger.warning(f'Redis not available, using memory storage: {e}')

    # Create simple fallback
    class FallbackStorage:
        def __init__(self):
            self._data = {}

        def get(self, key):
            return self._data.get(key)

        def setex(self, key, ttl, value):
            self._data[key] = value
            return True

        def delete(self, key):
            if key in self._data:
                del self._data[key]
            return True

    class FallbackManager:

        def __init__(self):
            self.redis = FallbackStorage()

    redis_manager = FallbackManager()


class DiscordService:
    """Discord service for managing voice channels for LoL matches."""

    def __init__(self):
        self.client: Optional[discord.Client] = None
        self.guild: Optional[Guild] = None
        self.category: Optional[CategoryChannel] = None
        self.connected = False
        self.connection_task: Optional[asyncio.Task] = None
        self.category_name = 'LoL Voice Chat'
        self.mock_mode = False
        self._match_channels_cache = {}  # Cache of channels by match_id

    async def connect(self) -> bool:
        """Connect to Discord or fallback to mock mode."""
        try:
            if not settings.DISCORD_BOT_TOKEN:
                logger.info(
                    'Discord bot token not configured - running in MOCK mode'
                )
                self.mock_mode = True
                return True
            logger.info('Attempting to connect to Discord...')
            # Create client with required intents
            intents = discord.Intents.default()
            intents.members = True
            intents.voice_states = True
            intents.guilds = True
            self.client = discord.Client(intents=intents)
            # Setup event handlers
            self.setup_event_handlers()

            @self.client.event
            async def on_ready():
                logger.info(f'Discord bot connected as {self.client.user}')
                self.connected = True
                await self._initialize_guild_and_category()

            @self.client.event
            async def on_disconnect():
                logger.warning('Discord bot disconnected')
                self.connected = False
            # Start connection in background
            self.connection_task = asyncio.create_task(self._connect_internal())
            # Wait for connection
            await asyncio.sleep(5)
            if not self.connected:
                logger.warning(
                    'Discord connection timeout - running in MOCK mode'
                )
                self.mock_mode = True
                await self.disconnect()
            return True
        except Exception as e:
            logger.error(f'Discord connection error: {e}')
            self.mock_mode = True
            return True

    def setup_event_handlers(self):
        """Setup Discord event handlers for automatic voice channel management."""
        if not self.client:
            return

        @self.client.event
        async def on_voice_state_update(member, before, after):
            """Automatically move players to their team channels."""
            try:
                # Ignore bot events
                if member.bot:
                    return
                # If user joined a voice channel
                if after.channel and after.channel != before.channel:
                    logger.info(
                        f'User {member.display_name} joined voice channel: '
                        f'{after.channel.name}'
                    )
                    # Find active matches for this user
                    user_key = f'user_discord:{member.id}'
                    match_data = redis_manager.redis.get(user_key)
                    if match_data:
                        match_info = json.loads(match_data)
                        match_id = match_info.get('match_id')
                        team_name = match_info.get('team_name')
                        if match_id and team_name:
                            # If user no longer has a match role, do not auto-move
                            role_prefix = f'LoL {match_id} -'
                            if not any(getattr(r, 'name', '').startswith(role_prefix) for r in member.roles):
                                return
                            # Find team voice channel
                            target_channel = await self.find_team_channel(
                                match_id,
                                team_name
                            )
                            if (
                                target_channel and target_channel.id != after.channel.id
                            ):
                                try:
                                    await member.move_to(target_channel)
                                    logger.info(
                                        f'Automatically moved '
                                        f'{member.display_name} to '
                                        f'{team_name} channel'
                                    )
                                except discord.Forbidden:
                                    logger.error(
                                        f'No permission to move '
                                        f'{member.display_name}'
                                    )
                                except discord.HTTPException as e:
                                    logger.error(
                                        f'Failed to move user: {e}'
                                    )
            except Exception as e:
                logger.error(f'Error in voice state update: {e}')

    async def find_team_channel(
        self,
        match_id: str,
        team_name: str
    ) -> Optional[VoiceChannel]:
        """Find voice channel for specific team in match."""
        if not self.guild or not self.category:
            return None
        channel_name = f'LoL Match {match_id} - {team_name}'
        for channel in self.category.voice_channels:
            if channel.name == channel_name:
                return channel
        return None

    async def _connect_internal(self):
        """Internal method to handle Discord connection."""
        try:
            await self.client.start(settings.DISCORD_BOT_TOKEN)
        except discord.LoginFailure:
            logger.error('Invalid Discord bot token')
        except discord.PrivilegedIntentsRequired:
            logger.error(
                'Bot requires privileged intents - enable in '
                'Discord Developer Portal'
            )
        except Exception as e:
            logger.error(f'Discord connection error: {e}')

    async def _initialize_guild_and_category(self):
        """Initialize guild and category for Discord with improved error handling."""
        if not self.connected or not self.client:
            return
        try:
            # Find guild with better error handling
            guild_id = None
            if settings.DISCORD_GUILD_ID:
                try:
                    guild_id = int(settings.DISCORD_GUILD_ID)
                    self.guild = self.client.get_guild(guild_id)
                    if self.guild:
                        logger.info(
                            f'Connected to guild: {self.guild.name} '
                            f'(ID: {self.guild.id})'
                        )
                        logger.info(
                            f'Guild member count: {self.guild.member_count}'
                        )
                    else:
                        logger.warning(
                            f'Guild with ID {settings.DISCORD_GUILD_ID} '
                            f'not found in bot\'s guilds'
                        )
                        # List available guilds for debugging
                        available_guilds = [
                            f'{g.name} (ID: {g.id})' for g in self.client.guilds
                        ]
                        logger.info(
                            f'Bot is in these guilds: {available_guilds}'
                        )
                        self.mock_mode = True
                        return
                except ValueError:
                    logger.error(
                        f'Invalid DISCORD_GUILD_ID format: '
                        f'{settings.DISCORD_GUILD_ID}'
                    )
                    self.mock_mode = True
                    return
            else:
                if self.client.guilds:
                    self.guild = self.client.guilds[0]
                    logger.info(
                        f'Using first available guild: {self.guild.name} '
                        f'(ID: {self.guild.id})'
                    )
                else:
                    logger.warning('Bot is not in any guilds')
                    self.mock_mode = True
                    return
            # Test member fetching capability
            try:
                # Try to fetch the bot itself as a test
                bot_member = self.guild.get_member(self.client.user.id)
                if bot_member:
                    logger.info(
                        f'Bot member found: {bot_member.display_name}'
                    )
                else:
                    logger.warning(
                        'Could not find bot member in guild - '
                        'possible permissions issue'
                    )
                # Check bot permissions
                bot_permissions = self.guild.me.guild_permissions
                required_permissions = [
                    'manage_roles',
                    'manage_channels',
                    'view_channel',
                    'connect',
                    'speak',
                    'move_members'
                ]
                missing_permissions = []
                for perm in required_permissions:
                    if not getattr(bot_permissions, perm):
                        missing_permissions.append(perm)
                if missing_permissions:
                    logger.warning(
                        f'Bot missing permissions: '
                        f'{", ".join(missing_permissions)}'
                    )
                else:
                    logger.info('Bot has all required permissions')
            except Exception as e:
                logger.error(f'Error checking bot permissions: {e}')
            # Create or find category
            self.category = await self._get_or_create_category()
            if not self.category:
                logger.warning('Failed to get/create category')
                self.mock_mode = True
                return
            # Initialize cache of existing channels
            await self._initialize_channel_cache()
            # Optional: clean up orphaned channels/roles (useful when REDIS_URL=memory://)
            if getattr(settings, 'DISCORD_GC_ON_STARTUP', True):
                try:
                    await self.garbage_collect_orphaned_matches(
                        max_age_hours=int(getattr(settings, 'DISCORD_GC_STALE_HOURS', 6)),
                        min_age_minutes=int(getattr(settings, 'DISCORD_GC_MIN_AGE_MINUTES', 10)),
                    )
                except Exception as e:
                    logger.debug(f'Orphan GC on startup skipped: {e}')
            logger.info('Discord service fully initialized')
        except Exception as e:
            logger.error(f'Error initializing Discord: {e}')
            self.mock_mode = True

    async def _initialize_channel_cache(self):
        """Initialize cache of existing match channels."""
        try:
            if not self.category:
                return
            logger.info('Initializing channel cache...')
            for channel in self.category.voice_channels:
                if (
                    'LoL Match' in channel.name and isinstance(channel, VoiceChannel)
                ):
                    # Extract match_id and team_name from channel name
                    # Format: 'LoL Match {match_id} - {team_name}'
                    parts = channel.name.split(' - ')
                    if len(parts) == 2:
                        match_part = parts[0].replace('LoL Match ', '').strip()
                        team_name = parts[1].strip()
                        if match_part and team_name:
                            if match_part not in self._match_channels_cache:
                                self._match_channels_cache[match_part] = {}
                            self._match_channels_cache[match_part][
                                team_name
                            ] = channel
                            logger.info(f'Cached channel: {channel.name}')
            logger.info(
                f'Channel cache initialized: '
                f'{len(self._match_channels_cache)} matches'
            )
        except Exception as e:
            logger.error(f'Error initializing channel cache: {e}')

    async def _get_or_create_category(self) -> Optional[CategoryChannel]:
        """Get or create category."""
        if not self.guild:
            return None
        try:
            # Look for existing category
            for category in self.guild.categories:
                if category.name == self.category_name:
                    logger.info(f'Found existing category: {category.name}')
                    return category
            # Create new category
            logger.info(f'Creating category: {self.category_name}')
            category = await self.guild.create_category(
                self.category_name,
                reason='Auto-created for LoL Voice Chat'
            )
            logger.info(f'Created category: {category.name}')
            return category
        except Exception as e:
            logger.error(f'Failed to get/create category: {e}')
            return None

    async def _get_or_create_team_role(
        self,
        match_id: str,
        team_name: str
    ) -> Optional[Role]:
        """Create or get a unique role for a team in a match."""
        if not self.guild:
            return None
        role_name = f'LoL {match_id} - {team_name}'
        try:
            # Look for existing role
            for role in self.guild.roles:
                if role.name == role_name:
                    logger.info(f'Found existing role: {role_name}')
                    return role
            # Create new role
            logger.info(f'Creating team role: {role_name}')
            color = (
                discord.Color.blue()
                if 'blue' in team_name.lower()
                else discord.Color.red()
            )
            team_role = await self.guild.create_role(
                name=role_name,
                color=color,
                hoist=False,
                mentionable=False,
                reason=f'Auto-created for {team_name} in LoL match {match_id}'
            )
            logger.info(f'Created team role: {team_role.name}')
            return team_role
        except Exception as e:
            logger.error(f'Failed to create team role: {e}')
            return None

    async def create_or_get_voice_channel(
        self,
        match_id: str,
        team_name: str
    ) -> Dict[str, Any]:
        """Create or get existing voice channel for a team in a match."""
        if (
            self.mock_mode or not self.connected or not self.guild or not self.category
        ):
            logger.info(
                f'MOCK: Creating voice channel for {team_name} in match {match_id}'
            )
            return self._create_mock_channel_data(match_id, team_name)
        try:
            channel_name = f'LoL Match {match_id} - {team_name}'
            # Check cache first
            if (
                match_id in self._match_channels_cache and (
                    team_name in self._match_channels_cache[match_id])
            ):
                existing_channel = self._match_channels_cache[match_id][team_name]
                logger.info(
                    f'Found cached channel for {team_name} in match {match_id}'
                )
                # Update invite
                invite = await existing_channel.create_invite(
                    max_uses=0,  # Unlimited uses
                    unique=False,
                    reason=f'Recreated invite for {team_name} in match {match_id}'
                )
                # Get role
                team_role = await self._get_or_create_team_role(match_id, team_name)
                return {
                    'channel_id': str(existing_channel.id),
                    'channel_name': channel_name,
                    'invite_url': invite.url,
                    'match_id': match_id,
                    'team_name': team_name,
                    'role_id': str(team_role.id) if team_role else '',
                    'mock': False,
                    'secured': True,
                    'existing': True,
                    'cached': True
                }
            # Look for existing channel in category
            existing_channel = None
            for channel in self.category.voice_channels:
                if channel.name == channel_name:
                    existing_channel = channel
                    logger.info(f'Found existing voice channel: {channel_name}')
                    # Update cache
                    if match_id not in self._match_channels_cache:
                        self._match_channels_cache[match_id] = {}
                    self._match_channels_cache[match_id][team_name] = channel
                    break
            # If channel already exists - return it
            if existing_channel:
                # Update permissions
                team_role = await self._get_or_create_team_role(match_id, team_name)
                if team_role:
                    overwrites = {
                        self.guild.default_role: discord.PermissionOverwrite(
                            view_channel=False,
                            connect=False
                        ),
                        team_role: discord.PermissionOverwrite(
                            view_channel=True,
                            connect=True,
                            speak=True
                        ),
                        self.guild.me: discord.PermissionOverwrite(
                            view_channel=True,
                            connect=True,
                            speak=True,
                            manage_channels=True,
                            manage_roles=True
                        )
                    }
                    await existing_channel.edit(overwrites=overwrites)
                # Create invite
                invite = await existing_channel.create_invite(
                    max_uses=0,
                    unique=False,
                    reason=f'Recreated invite for {team_name} in match {match_id}'
                )
                return {
                    'channel_id': str(existing_channel.id),
                    'channel_name': channel_name,
                    'invite_url': invite.url,
                    'match_id': match_id,
                    'team_name': team_name,
                    'role_id': str(team_role.id) if team_role else '',
                    'mock': False,
                    'secured': True,
                    'existing': True
                }
            # Create new channel only if it doesn't exist
            logger.info(f'Creating NEW voice channel: {channel_name}')
            # Create team role
            team_role = await self._get_or_create_team_role(match_id, team_name)
            if not team_role:
                logger.error('Failed to create team role, falling back to mock')
                return self._create_mock_channel_data(match_id, team_name)
            # Setup permissions
            overwrites = {
                self.guild.default_role: discord.PermissionOverwrite(
                    view_channel=False,
                    connect=False
                ),
                team_role: discord.PermissionOverwrite(
                    view_channel=True,
                    connect=True,
                    speak=True
                ),
                self.guild.me: discord.PermissionOverwrite(
                    view_channel=True,
                    connect=True,
                    speak=True,
                    manage_channels=True,
                    manage_roles=True
                )
            }
            # Create voice channel
            voice_channel = await self.guild.create_voice_channel(
                name=channel_name,
                category=self.category,
                overwrites=overwrites,
                reason=(
                    f'Secured voice chat for {team_name} '
                    f'in LoL match {match_id}'
                )
            )
            # Update cache
            if match_id not in self._match_channels_cache:
                self._match_channels_cache[match_id] = {}
            self._match_channels_cache[match_id][team_name] = voice_channel
            # Create invite
            invite = await voice_channel.create_invite(
                max_uses=0,
                unique=False,
                reason='Auto-generated for secured LoL match'
            )

            logger.info(f'Created new Discord voice channel: {voice_channel.name}')
            return {
                'channel_id': str(voice_channel.id),
                'channel_name': channel_name,
                'invite_url': invite.url,
                'match_id': match_id,
                'team_name': team_name,
                'role_id': str(team_role.id),
                'mock': False,
                'secured': True,
                'existing': False
            }
        except Exception as e:
            logger.error(f'Failed to create/get Discord channel: {e}')
            return self._create_mock_channel_data(match_id, team_name)

    def _create_mock_channel_data(
        self,
        match_id: str,
        team_name: str
    ) -> Dict[str, Any]:
        """Create mock channel data for development."""
        mock_channel_id = (
            f'mock_{match_id}_{team_name.lower().replace(" ", "_")}'
        )
        return {
            'channel_id': mock_channel_id,
            'channel_name': f'LoL Match {match_id} - {team_name}',
            'invite_url': f'https://discord.gg/mock-invite-{mock_channel_id}',
            'match_id': match_id,
            'team_name': team_name,
            'role_id': f'mock_role_{mock_channel_id}',
            'mock': True,
            'secured': False,
            'existing': False,
            'note': (
                'This is test data. For real Discord channels, '
                'install Discord and configure the bot.'
            )
        }

    async def create_or_get_team_channels(
        self,
        match_id: str,
        blue_team: List[str],
        red_team: List[str]
    ) -> Dict[str, Any]:
        """Create or get existing channels for both teams with role-based access."""
        logger.info(f'Creating or getting team channels for match {match_id}')
        # One channel per team, don't create new if already exists
        blue_channel = await self.create_or_get_voice_channel(
            match_id,
            'Blue Team'
        )
        await asyncio.sleep(0.5)
        red_channel = await self.create_or_get_voice_channel(
            match_id,
            'Red Team'
        )
        result = {
            'match_id': match_id,
            'blue_team': blue_channel,
            'red_team': red_channel,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'mock_mode': self.mock_mode,
            'secured': not self.mock_mode,
            'unique_channels': True  # Guarantee channels are unique per match
        }
        if self.mock_mode:
            result['note'] = (
                'Development mode: using Discord test data'
            )
        else:
            result['note'] = (
                'Channels secured: players only have access to their team channels'
            )
        # Log for debugging
        logger.info(f'Team channels for match {match_id}:')
        logger.info(
            f'Blue channel: {blue_channel.get("channel_name")} '
            f'(existing: {blue_channel.get("existing")})'
        )
        logger.info(
            f'Red channel: {red_channel.get("channel_name")} '
            f'(existing: {red_channel.get("existing")})'
        )
        return result

    async def assign_player_to_team(
        self,
        discord_user_id: int,
        match_id: str,
        team_name: str
    ) -> bool:
        """Assign a Discord user to a team with enhanced user discovery."""
        if self.mock_mode:
            logger.info(
                f'MOCK: Assigning user {discord_user_id} '
                f'to {team_name} in match {match_id}'
            )
            return True
        if not self.connected or not self.guild:
            logger.warning(
                'Discord not connected - cannot assign user to team'
            )
            return False
        try:
            logger.info(
                f'Assigning user {discord_user_id} '
                f'to {team_name} in match {match_id}'
            )
            # Multiple methods to find member
            member = None
            # Method 1: Check cache first
            member = self.guild.get_member(discord_user_id)
            if member:
                logger.info(f'Found user {member.display_name} in guild cache')
            # Method 2: Fetch from API if not in cache
            if not member:
                try:
                    logger.info(
                        f'Fetching user {discord_user_id} from Discord API...'
                    )
                    member = await self.guild.fetch_member(discord_user_id)
                    if member:
                        logger.info(
                            f'Fetched user {member.display_name} '
                            f'from Discord API'
                        )
                except discord.NotFound:
                    logger.error(
                        f'Discord user {discord_user_id} not found '
                        f'in guild {self.guild.name}'
                    )
                    # Create an invite for the user to join the server
                    await self._create_server_invite_for_user(
                        match_id,
                        team_name,
                        discord_user_id
                    )
                    return False
                except discord.Forbidden:
                    logger.error(
                        f'Bot doesn\'t have permission to fetch member '
                        f'{discord_user_id}'
                    )
                    logger.error(
                        'Check if bot has \'Server Members Intent\' '
                        'enabled in Discord Developer Portal'
                    )
                    return False
                except discord.HTTPException as e:
                    logger.error(f'Discord API error fetching member: {e}')
                    return False
            if not member:
                logger.error(
                    f'Could not find Discord user {discord_user_id} '
                    f'in guild {self.guild.name}'
                )
                logger.info(
                    f'Guild members in cache: {len(self.guild.members)}'
                )
                # Try one more method - search in members list
                for guild_member in self.guild.members:
                    if guild_member.id == discord_user_id:
                        member = guild_member
                        logger.info(
                            f'Found user {member.display_name} '
                            f'in members list iteration'
                        )
                        break
                if not member:
                    logger.error(
                        f'User {discord_user_id} not found in any member list'
                    )
                    await self._create_server_invite_for_user(
                        match_id,
                        team_name,
                        discord_user_id
                    )
                    return False
            # Find team role
            role_name = f'LoL {match_id} - {team_name}'
            team_role = None
            logger.info(f'Searching for role: {role_name}')
            for role in self.guild.roles:
                if role.name == role_name:
                    team_role = role
                    logger.info(f'Found team role: {role.name} (ID: {role.id})')
                    break
            if not team_role:
                logger.error(f'Team role not found: {role_name}')
                # Try to create the role
                team_role = await self._get_or_create_team_role(
                    match_id,
                    team_name
                )
                if not team_role:
                    logger.error('Failed to create team role')
                    return False
            # Check if bot has permission to manage roles
            if not self.guild.me.guild_permissions.manage_roles:
                logger.error('Bot doesn\'t have \'Manage Roles\' permission')
                return False
            # Check if bot's role is high enough to assign this role
            if self.guild.me.top_role <= team_role:
                logger.error(
                    f'Bot\'s role ({self.guild.me.top_role.name}) '
                    f'is not high enough to assign role {role_name}'
                )
                logger.error('Move bot\'s role higher in role hierarchy')
                return False
            # Check if member already has the role
            if team_role in member.roles:
                logger.info(
                    f'User {member.display_name} already has role '
                    f'{team_role.name}'
                )
                # But still save match info
                user_key = f'user_discord:{discord_user_id}'
                match_info = {
                    'match_id': match_id,
                    'team_name': team_name,
                    'assigned_at': datetime.now(timezone.utc).isoformat()
                }
                redis_manager.redis.setex(
                    user_key,
                    3600,
                    json.dumps(match_info)
                )
                return True
            # Assign role
            try:
                await member.add_roles(
                    team_role,
                    reason=f'Assigned to {team_name} in match {match_id}'
                )
                logger.info(
                    f'Assigned {member.display_name} to role {team_role.name}'
                )
                # Save match info for automatic voice channel management
                user_key = f'user_discord:{discord_user_id}'
                match_info = {
                    'match_id': match_id,
                    'team_name': team_name,
                    'assigned_at': datetime.now(timezone.utc).isoformat()
                }
                redis_manager.redis.setex(
                    user_key,
                    3600,
                    json.dumps(match_info)
                )
                return True
            except discord.Forbidden:
                logger.error(
                    f'No permission to assign role to {member.display_name}'
                )
                logger.error('Check role hierarchy and bot permissions')
                return False
            except discord.HTTPException as e:
                logger.error(f'Failed to assign role: {e}')
                return False
        except Exception as e:
            logger.error(f'Failed to assign player to team: {e}')
            return False



    async def move_member_to_team_channel_if_in_voice(
        self,
        discord_user_id: int,
        match_id: str,
        team_name: str
    ) -> bool:
        """If the user is currently in *any* voice channel (e.g. Waiting Room),
        move them into their team voice channel for the given match.

        This fixes the UX where a user sits in Waiting Room, starts a match,
        gets the role assigned, but doesn't get moved unless they re-join.
        """
        if self.mock_mode:
            logger.info(
                f'MOCK: Moving user {discord_user_id} to {team_name} channel for match {match_id}'
            )
            return True

        if not self.connected or not self.guild:
            logger.warning('Discord not connected - cannot move user')
            return False

        try:
            member = self.guild.get_member(discord_user_id)
            if not member:
                try:
                    member = await self.guild.fetch_member(discord_user_id)
                except Exception:
                    member = None

            if not member:
                logger.warning(f'Could not find member {discord_user_id} to move')
                return False

            # Must be connected to voice to move
            if not member.voice or not member.voice.channel:
                logger.info(f'User {member.display_name} is not in a voice channel; nothing to move')
                return False

            # Find target channel by name
            target_name = f'LoL Match {match_id} - {team_name}'
            target_channel = None

            # Prefer category voice channels if available
            search_channels = []
            if self.category:
                search_channels = list(getattr(self.category, 'voice_channels', []) or [])
            if not search_channels:
                search_channels = [c for c in self.guild.channels if isinstance(c, VoiceChannel)]

            for ch in search_channels:
                try:
                    if isinstance(ch, VoiceChannel) and ch.name == target_name:
                        target_channel = ch
                        break
                except Exception:
                    continue

            if not target_channel:
                logger.warning(f'Target team voice channel not found: {target_name}')
                return False

            if member.voice.channel.id == target_channel.id:
                logger.info(f'User {member.display_name} already in target channel')
                return True

            try:
                await member.move_to(target_channel)
                logger.info(f'Automatically moved {member.display_name} to {team_name} channel')
                return True
            except discord.Forbidden:
                logger.error('Bot lacks permission to move members (Move Members)')
                return False
            except discord.HTTPException as e:
                logger.error(f'Failed to move member: {e}')
                return False
        except Exception as e:
            logger.error(f'Error auto-moving member: {e}')
            return False



    async def _get_team_role(
        self,
        match_id: str,
        team_name: str
    ) -> Optional[Role]:
        """Get existing team role for match/team without creating it."""
        if not self.guild:
            return None
        role_name = f'LoL {match_id} - {team_name}'
        for role in self.guild.roles:
            if role.name == role_name:
                return role
        return None

    async def remove_player_from_match(
        self,
        discord_user_id: int,
        match_id: str,
        team_name: Optional[str] = None
    ) -> bool:
        """Remove a single player from match roles/channels (early leave, crash, etc.)."""
        if self.mock_mode:
            logger.info(
                f'MOCK: Removing user {discord_user_id} from match {match_id} ({team_name})'
            )
            return True

        if not self.connected or not self.guild:
            logger.warning('Discord not connected; cannot remove player')
            return False

        try:
            member = self.guild.get_member(discord_user_id)
            if not member:
                try:
                    member = await self.guild.fetch_member(discord_user_id)
                except Exception:
                    member = None

            if not member:
                logger.warning(f'Could not find member {discord_user_id} in guild')
                return False

            # Remove role(s)
            roles_to_remove: List[Role] = []
            if team_name:
                role = await self._get_team_role(match_id, team_name)
                if role:
                    roles_to_remove.append(role)
            else:
                # If team unknown, try remove both team roles
                for tn in ('Blue Team', 'Red Team'):
                    role = await self._get_team_role(match_id, tn)
                    if role:
                        roles_to_remove.append(role)

            if roles_to_remove:
                try:
                    await member.remove_roles(
                        *roles_to_remove,
                        reason=f'LoL match {match_id}: player left early'
                    )
                    logger.info(
                        f'Removed {len(roles_to_remove)} match roles from {member.display_name}'
                    )
                except Exception as e:
                    logger.warning(f'Failed to remove roles: {e}')

            # Disconnect from match channels if currently in one
            try:
                if member.voice and member.voice.channel:
                    ch = member.voice.channel
                    if f'LoL Match {match_id}' in ch.name:
                        # Prefer moving to Waiting Room if exists
                        waiting = None
                        if self.category:
                            for vc in self.category.voice_channels:
                                if isinstance(vc, VoiceChannel) and vc.name.lower() == 'waiting room':
                                    waiting = vc
                                    break
                        try:
                            await member.move_to(waiting)
                        except Exception:
                            await member.move_to(None)
                        logger.info(
                            f'Disconnected {member.display_name} from match voice channel'
                        )
            except Exception as e:
                logger.warning(f'Failed to disconnect member from voice: {e}')

            return True
        except Exception as e:
            logger.error(f'Error removing player from match: {e}')
            return False


    async def match_has_active_players(self, match_id: str) -> bool:
        """Return True if any app users still appear active for this match.

        We consider a match "active" if:
        - Any member still has one of the match team roles, OR
        - Any member is currently inside one of the match voice channels.

        Conservative behavior:
        - If we cannot reliably determine state (e.g., roles/channels not found),
          we return True to avoid accidental deletion.
        """
        if self.mock_mode:
            return False
        if not self.connected or not self.guild:
            return True
        try:
            roles = []
            for tn in ('Blue Team', 'Red Team'):
                role = await self._get_team_role(match_id, tn)
                if role:
                    roles.append(role)

            role_members_total = None
            if roles:
                try:
                    role_members_total = sum(len(r.members) for r in roles)
                except Exception:
                    role_members_total = None

            # Also check current members in match voice channels (usually reliable)
            voice_members_total = None
            try:
                if self.category:
                    match_channels = [
                        ch for ch in self.category.voice_channels
                        if isinstance(ch, VoiceChannel) and f'LoL Match {match_id}' in ch.name
                    ]
                    if match_channels:
                        voice_members_total = sum(len(ch.members) for ch in match_channels)
            except Exception:
                voice_members_total = None

            # If we have at least one reliable signal:
            active_counts = [c for c in (role_members_total, voice_members_total) if c is not None]
            if active_counts:
                return sum(active_counts) > 0

            # No reliable signal -> don't risk deletion
            return True
        except Exception as e:
            logger.warning(f'Active player check error: {e}')
            return True


    async def garbage_collect_orphaned_matches(
        self,
        max_age_hours: int = 6,
        min_age_minutes: int = 10
    ) -> None:
        """Delete stale/empty match channels & roles left behind (e.g., app restart with memory://).

        Safe rules (won't delete active matches):
        - Match voice channels are EMPTY (no members in them)
        - Both team roles have 0 members (or roles don't exist)
        - Channels are older than min_age_minutes and max_age_hours threshold
        """
        if self.mock_mode or not self.connected or not self.guild or not self.category:
            return
        try:
            now = datetime.now(timezone.utc)
            match_to_channels: Dict[str, List[VoiceChannel]] = {}

            for ch in list(self.category.voice_channels):
                if not isinstance(ch, VoiceChannel):
                    continue
                name = getattr(ch, 'name', '') or ''
                if not name.startswith('LoL Match '):
                    continue
                # Format: 'LoL Match {match_id} - {Team}'
                parts = name.split(' - ')
                if not parts:
                    continue
                match_id = parts[0].replace('LoL Match ', '').strip()
                if not match_id:
                    continue
                match_to_channels.setdefault(match_id, []).append(ch)

            if not match_to_channels:
                return

            for match_id, channels in match_to_channels.items():
                try:
                    # Age gate
                    created_ats = [getattr(ch, 'created_at', None) for ch in channels]
                    created_ats = [dt for dt in created_ats if dt is not None]
                    if created_ats:
                        age = now - min(created_ats)
                    else:
                        # If Discord didn't provide created_at (rare), skip to be safe
                        continue

                    if age < timedelta(minutes=min_age_minutes):
                        continue
                    if age < timedelta(hours=max_age_hours):
                        continue

                    # Must be empty channels
                    if any(len(ch.members) > 0 for ch in channels):
                        continue

                    # Must have no members in match roles
                    roles = []
                    for tn in ('Blue Team', 'Red Team'):
                        role = await self._get_team_role(match_id, tn)
                        if role:
                            roles.append(role)

                    if any(len(r.members) > 0 for r in roles):
                        continue

                    logger.info(
                        f'Orphan GC: deleting stale match resources for {match_id} '
                        f'(age={age}, channels={len(channels)})'
                    )
                    await self.cleanup_match_channels({'match_id': match_id})

                except Exception as e:
                    logger.debug(f'Orphan GC skipped for {match_id}: {e}')
                    continue
        except Exception as e:
            logger.debug(f'Orphan GC failed: {e}')



    async def _create_server_invite_for_user(
        self,
        match_id: str,
        team_name: str,
        discord_user_id: int
    ):
        """Create a server invite and notify about the need to join the server."""
        try:
            if not self.guild:
                return
            # Create an invite for the user
            invite_channel = (
                self.guild.system_channel or next(
                    (
                        ch for ch in self.guild.text_channels
                        if ch.permissions_for(self.guild.me).create_instant_invite
                    ),
                    None
                )
            )
            if invite_channel:
                invite = await invite_channel.create_invite(
                    max_uses=1,
                    unique=True,
                    reason=f'Invite for LoL match {match_id} - {team_name}'
                )
                logger.info(
                    f'Created server invite for user {discord_user_id}: '
                    f'{invite.url}'
                )
                # Store the invite for the user
                invite_key = f'server_invite:{discord_user_id}'
                redis_manager.redis.setex(invite_key, 3600, invite.url)
                # You could also send a DM to the user if possible
                await self._send_dm_to_user(
                    discord_user_id,
                    invite.url,
                    match_id,
                    team_name
                )
        except Exception as e:
            logger.error(f'Failed to create server invite: {e}')

    async def _send_dm_to_user(
        self,
        discord_user_id: int,
        invite_url: str,
        match_id: str,
        team_name: str
    ):
        """Send a direct message to the user with server invite."""
        try:
            if not self.guild:
                return
            member = self.guild.get_member(discord_user_id)
            if not member:
                # Try to fetch member
                try:
                    member = await self.guild.fetch_member(discord_user_id)
                except Exception:
                    return
            if member:
                embed = discord.Embed(
                    title='Join server for voice chat',
                    description=(
                        f'To participate in voice chat for match **{match_id}** '
                        f'with team **{team_name}**, please join our Discord server:'
                    ),
                    color=0x7289da
                )
                embed.add_field(
                    name='Join link',
                    value=invite_url,
                    inline=False
                )
                embed.add_field(
                    name='Instructions',
                    value=(
                        '1. Click the link above\n'
                        '2. Join the server\n'
                        '3. Return to the game'
                    ),
                    inline=False
                )
                embed.set_footer(text='LoL Voice Chat')
                await member.send(embed=embed)
                logger.info(
                    f'Sent DM with server invite to {member.display_name}'
                )
        except discord.Forbidden:
            logger.warning(
                f'Cannot send DM to user {discord_user_id} (DMs closed)'
            )
        except Exception as e:
            logger.error(f'Failed to send DM: {e}')

    async def cleanup_team_roles(self, match_id: str):
        """Cleanup roles after match ends."""
        if not self.connected or not self.guild:
            return
        try:
            roles_to_delete = []
            for role in self.guild.roles:
                if f'LoL {match_id} -' in role.name:
                    roles_to_delete.append(role)
            for role in roles_to_delete:
                try:
                    await role.delete(reason=f'LoL match {match_id} ended')
                    logger.info(f'Deleted role: {role.name}')
                except Exception as e:
                    logger.error(f'Failed to delete role {role.name}: {e}')
        except Exception as e:
            logger.error(f'Error during role cleanup: {e}')

    async def cleanup_match_channels(self, match_data: Dict[str, Any]):
        """Cleanup channels and roles after match ends with improved cleanup."""
        logger.info(f'Starting cleanup for match: {match_data}')
        if self.mock_mode:
            logger.info(
                f'MOCK: Cleaning up channels for match '
                f'{match_data.get("match_id")}'
            )
            return
        try:
            match_id = match_data.get('match_id')
            if not match_id:
                logger.warning('No match ID provided for cleanup')
                return
            logger.info(
                f'Looking for channels to cleanup for match {match_id}'
            )
            # Find and delete all channels of this match in the category
            if self.category:
                channels_to_delete = []
                for channel in self.category.voice_channels:
                    if (
                        isinstance(
                            channel, VoiceChannel
                        ) and f'LoL Match {match_id}' in channel.name
                    ):
                        channels_to_delete.append(channel)
                logger.info(f'Found {len(channels_to_delete)} channels to delete')
                # Delete channels
                for channel in channels_to_delete:
                    try:
                        # First disconnect all members
                        members = channel.members
                        if members:
                            logger.info(
                                f'Disconnecting {len(members)} members '
                                f'from {channel.name}'
                            )
                            for member in members:
                                try:
                                    await member.move_to(None)
                                except Exception as e:
                                    logger.warning(
                                        f'Failed to disconnect '
                                        f'{member.display_name}: {e}'
                                    )
                        # Delete channel
                        await channel.delete(
                            reason=f'LoL match {match_id} ended'
                        )
                        logger.info(f'Deleted channel: {channel.name}')
                    except discord.NotFound:
                        logger.warning(
                            f'Channel {channel.name} not found '
                            f'(already deleted)'
                        )
                    except Exception as e:
                        logger.error(
                            f'Failed to delete channel {channel.name}: {e}'
                        )
            # Cleanup roles
            logger.info(f'Cleaning up roles for match {match_id}')
            await self.cleanup_team_roles(match_id)
            # Clear cache for this match
            if match_id in self._match_channels_cache:
                del self._match_channels_cache[match_id]
                logger.info(f'Cleared cache for match {match_id}')

            logger.info(f'Cleanup completed for match {match_id}')

        except Exception as e:
            logger.error(f'Failed to cleanup match channels and roles: {e}')

    async def disconnect_all_members(self, channel_id: int):
        """Disconnect all members from a voice channel."""
        if self.mock_mode or not self.client:
            return
        try:
            channel = self.client.get_channel(channel_id)
            if isinstance(channel, VoiceChannel):
                members = channel.members
                if members:
                    logger.info(
                        f'Disconnecting {len(members)} members '
                        f'from channel {channel.name}'
                    )
                    for member in members:
                        try:
                            await member.move_to(None)  # Disconnect user
                            logger.debug(
                                f'Disconnected {member.display_name} '
                                f'from voice channel'
                            )
                        except Exception as e:
                            logger.warning(
                                f'Failed to disconnect '
                                f'{member.display_name}: {e}'
                            )
                    logger.info(
                        f'Successfully disconnected all members '
                        f'from {channel.name}'
                    )
                else:
                    logger.info(
                        f'No members in channel {channel.name} to disconnect'
                    )
        except Exception as e:
            logger.error(
                f'Failed to disconnect members from channel {channel_id}: {e}'
            )

    async def delete_voice_channel(self, channel_id: int):
        """Delete a voice channel by ID, first disconnecting all members."""
        if self.mock_mode or not self.client:
            return
        try:
            channel = self.client.get_channel(channel_id)
            if isinstance(channel, VoiceChannel):
                # First disconnect all members
                await self.disconnect_all_members(channel_id)
                # Then delete channel
                await channel.delete(reason='LoL match ended')
                logger.info(
                    f'Deleted Discord voice channel: {channel.name} '
                    f'(ID: {channel_id})'
                )
        except discord.NotFound:
            logger.warning(
                f'Channel {channel_id} not found (already deleted)'
            )
        except Exception as e:
            logger.error(f'Failed to delete Discord channel {channel_id}: {e}')

    async def force_disconnect_all_matches(self):
        """Force disconnect all members from all LoL voice channels."""
        if (
            self.mock_mode or not self.guild or not self.category
        ):
            logger.info('MOCK: Force disconnect all matches')
            return {'disconnected_members': 0, 'channels_processed': 0}

        try:
            disconnected_count = 0
            channel_count = 0

            for channel in self.category.voice_channels:
                if (
                    'LoL Match' in channel.name and isinstance(channel, VoiceChannel)
                ):
                    channel_count += 1
                    members = channel.members
                    if members:
                        logger.info(
                            f'Force disconnecting {len(members)} members '
                            f'from {channel.name}'
                        )
                        for member in members:
                            try:
                                await member.move_to(None)
                                disconnected_count += 1
                            except Exception as e:
                                logger.warning(
                                    f'Failed to force disconnect '
                                    f'{member.display_name}: {e}'
                                )

            logger.info(
                f'Force disconnected {disconnected_count} members '
                f'from {channel_count} LoL channels'
            )
            return {
                'disconnected_members': disconnected_count,
                'channels_processed': channel_count
            }
        except Exception as e:
            logger.error(f'Failed to force disconnect all matches: {e}')
            return None

    async def disconnect(self):
        """Disconnect from Discord."""
        try:
            if self.connection_task:
                self.connection_task.cancel()
                try:
                    await self.connection_task
                except asyncio.CancelledError:
                    pass
            if self.client:
                await self.client.close()
            self.connected = False
            self.mock_mode = False
            self._match_channels_cache = {}  # Clear cache
            logger.info('Discord service disconnected')
        except Exception as e:
            logger.error(f'Error during Discord disconnect: {e}')

    def get_status(self) -> Dict[str, Any]:
        """Get Discord service status."""
        return {
            'connected': self.connected,
            'mock_mode': self.mock_mode,
            'guild_available': self.guild is not None,
            'category_available': self.category is not None,
            'cached_matches': len(self._match_channels_cache),
            'status': (
                'mock' if self.mock_mode
                else 'connected' if self.connected
                else 'disconnected'
            )
        }


discord_service = DiscordService()
