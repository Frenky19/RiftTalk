import asyncio
import discord
import logging
import json
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from discord import Guild, VoiceChannel, CategoryChannel, Role
from app.config import settings
from app.database import redis_manager

logger = logging.getLogger(__name__)


class DiscordService:
    """Discord service for managing voice channels for LoL matches."""

    def __init__(self):
        self.client: Optional[discord.Client] = None
        self.guild: Optional[Guild] = None
        self.category: Optional[CategoryChannel] = None
        self.connected = False
        self.connection_task: Optional[asyncio.Task] = None
        self.category_name = "LoL Voice Chat"
        self.mock_mode = False

    async def connect(self) -> bool:
        """Connect to Discord or fallback to mock mode."""
        try:
            if not settings.DISCORD_BOT_TOKEN:
                logger.info("🔶 Discord bot token not configured - running in MOCK mode")
                self.mock_mode = True
                return True
            logger.info("🔄 Attempting to connect to Discord...")
            # Create client with required intents
            intents = discord.Intents.default()
            intents.members = True
            intents.voice_states = True
            intents.guilds = True
            intents.voice_states = True

            self.client = discord.Client(intents=intents)
            
            # Setup event handlers
            self.setup_event_handlers()

            @self.client.event
            async def on_ready():
                logger.info(f"✅ Discord bot connected as {self.client.user}")
                self.connected = True
                await self._initialize_guild_and_category()

            @self.client.event
            async def on_disconnect():
                logger.warning("🔌 Discord bot disconnected")
                self.connected = False
                
            # Start connection in background
            self.connection_task = asyncio.create_task(self._connect_internal())
            # Wait for connection
            await asyncio.sleep(5)
            if not self.connected:
                logger.warning("⚠️ Discord connection timeout - running in MOCK mode")
                self.mock_mode = True
                await self.disconnect()
            return True

        except Exception as e:
            logger.error(f"❌ Discord connection error: {e}")
            self.mock_mode = True
            return True

    def setup_event_handlers(self):
        """Setup Discord event handlers for automatic voice channel management."""
        if not self.client:
            return

        @self.client.event
        async def on_voice_state_update(member, before, after):
            """Automatically move players to their team channels when they join any voice channel."""
            try:
                # Игнорируем события от бота
                if member.bot:
                    return

                # Если пользователь подключился к голосовому каналу
                if after.channel and after.channel != before.channel:
                    logger.info(f"👤 User {member.display_name} joined voice channel: {after.channel.name}")
                    
                    # Ищем активные матчи для этого пользователя
                    user_key = f"user_discord:{member.id}"
                    match_data = redis_manager.redis.get(user_key)
                    
                    if match_data:
                        match_info = json.loads(match_data)
                        match_id = match_info.get('match_id')
                        team_name = match_info.get('team_name')
                        
                        if match_id and team_name:
                            # Ищем голосовой канал команды
                            target_channel = await self.find_team_channel(match_id, team_name)
                            if target_channel and target_channel.id != after.channel.id:
                                try:
                                    await member.move_to(target_channel)
                                    logger.info(f"✅ Automatically moved {member.display_name} to {team_name} channel")
                                except discord.Forbidden:
                                    logger.error(f"❌ No permission to move {member.display_name}")
                                except discord.HTTPException as e:
                                    logger.error(f"❌ Failed to move user: {e}")
                
            except Exception as e:
                logger.error(f"❌ Error in voice state update: {e}")

    async def find_team_channel(self, match_id: str, team_name: str) -> Optional[VoiceChannel]:
        """Find voice channel for specific team in match."""
        if not self.guild or not self.category:
            return None
            
        channel_name = f"LoL Match {match_id} - {team_name}"
        for channel in self.category.voice_channels:
            if channel.name == channel_name:
                return channel
        return None

    async def _connect_internal(self):
        """Internal method to handle Discord connection."""
        try:
            await self.client.start(settings.DISCORD_BOT_TOKEN)
        except discord.LoginFailure:
            logger.error("❌ Invalid Discord bot token")
        except discord.PrivilegedIntentsRequired:
            logger.error("❌ Bot requires privileged intents - enable in Discord Developer Portal")
        except Exception as e:
            logger.error(f"❌ Discord connection error: {e}")

    async def _initialize_guild_and_category(self):
        """Initialize guild and category for Discord."""
        if not self.connected or not self.client:
            return

        try:
            # Find guild
            if settings.DISCORD_GUILD_ID:
                guild_id = int(settings.DISCORD_GUILD_ID)
                self.guild = self.client.get_guild(guild_id)
                if self.guild:
                    logger.info(f"✅ Connected to guild: {self.guild.name}")
                else:
                    logger.warning(f"⚠️ Guild with ID {settings.DISCORD_GUILD_ID} not found")
                    self.mock_mode = True
                    return
            else:
                if self.client.guilds:
                    self.guild = self.client.guilds[0]
                    logger.info(f"✅ Using first available guild: {self.guild.name}")
                else:
                    logger.warning("⚠️ Bot is not in any guilds")
                    self.mock_mode = True
                    return

            # Create or find category
            self.category = await self._get_or_create_category()
            if not self.category:
                logger.warning("⚠️ Failed to get/create category")
                self.mock_mode = True
                return

            logger.info("✅ Discord service fully initialized")

        except Exception as e:
            logger.error(f"❌ Error initializing Discord: {e}")
            self.mock_mode = True

    async def _get_or_create_category(self) -> Optional[CategoryChannel]:
        """Get or create category."""
        if not self.guild:
            return None
        try:
            # Look for existing category
            for category in self.guild.categories:
                if category.name == self.category_name:
                    logger.info(f"✅ Found existing category: {category.name}")
                    return category
            # Create new category
            logger.info(f"🔄 Creating category: {self.category_name}")
            category = await self.guild.create_category(
                self.category_name,
                reason="Auto-created for LoL Voice Chat"
            )
            logger.info(f"✅ Created category: {category.name}")
            return category
        except Exception as e:
            logger.error(f"❌ Failed to get/create category: {e}")
            return None

    async def _get_or_create_team_role(self, match_id: str, team_name: str) -> Optional[Role]:
        """Create or get a unique role for a team in a match."""
        if not self.guild:
            return None
        role_name = f"LoL {match_id} - {team_name}"
        try:
            # Look for existing role
            for role in self.guild.roles:
                if role.name == role_name:
                    logger.info(f"✅ Found existing role: {role_name}")
                    return role
            # Create new role
            logger.info(f"🔄 Creating team role: {role_name}")
            color = discord.Color.blue() if "blue" in team_name.lower() else discord.Color.red()
            team_role = await self.guild.create_role(
                name=role_name,
                color=color,
                hoist=False,
                mentionable=False,
                reason=f"Auto-created for {team_name} in LoL match {match_id}"
            )
            logger.info(f"✅ Created team role: {team_role.name}")
            return team_role
        except Exception as e:
            logger.error(f"❌ Failed to create team role: {e}")
            return None

    async def create_voice_channel(self, match_id: str, team_name: str) -> Dict[str, Any]:
        """Create voice channel with proper access restrictions."""
        if self.mock_mode or not self.connected or not self.guild or not self.category:
            logger.info(f"🎮 MOCK: Creating voice channel for {team_name} in match {match_id}")
            return self._create_mock_channel_data(match_id, team_name)
        try:
            channel_name = f"LoL Match {match_id} - {team_name}"
            # Create team role
            team_role = await self._get_or_create_team_role(match_id, team_name)
            if not team_role:
                logger.error("❌ Failed to create team role, falling back to mock")
                return self._create_mock_channel_data(match_id, team_name)
            # Configure permission overwrites
            overwrites = {
                # Deny access for everyone by default
                self.guild.default_role: discord.PermissionOverwrite(
                    view_channel=False,
                    connect=False
                ),
                # Allow access for team members
                team_role: discord.PermissionOverwrite(
                    view_channel=True,
                    connect=True,
                    speak=True
                ),
                # Bot has full access
                self.guild.me: discord.PermissionOverwrite(
                    view_channel=True,
                    connect=True,
                    speak=True,
                    manage_channels=True,
                    manage_roles=True
                )
            }
            # Check for existing channels
            existing_channel = None
            for channel in self.category.voice_channels:
                if (channel.name == channel_name or (
                    f"match {match_id}"
                ) in channel.name.lower() and team_name in channel.name):
                    existing_channel = channel
                    break
            if existing_channel:
                logger.info(f"✅ Voice channel already exists: {existing_channel.name}")
                # Update permissions for existing channel
                await existing_channel.edit(overwrites=overwrites)
                invite = await existing_channel.create_invite(
                    max_uses=5,
                    unique=True,
                    reason="Auto-regenerated for LoL match"
                )
                return {
                    "channel_id": str(existing_channel.id),
                    "channel_name": channel_name,
                    "invite_url": invite.url,
                    "match_id": match_id,
                    "team_name": team_name,
                    "role_id": str(team_role.id),
                    "mock": False,
                    "secured": True
                }
            logger.info(f"🔄 Creating secured voice channel: {channel_name}")
            # Create voice channel with restrictions
            voice_channel = await self.guild.create_voice_channel(
                name=channel_name,
                category=self.category,
                overwrites=overwrites,
                reason=f"Secured voice chat for {team_name} in LoL match {match_id}"
            )
            # Create invite
            invite = await voice_channel.create_invite(
                max_uses=5,
                unique=True,
                reason="Auto-generated for secured LoL match"
            )
            logger.info(f"✅ Created secured Discord voice channel: {voice_channel.name}")
            return {
                "channel_id": str(voice_channel.id),
                "channel_name": channel_name,
                "invite_url": invite.url,
                "match_id": match_id,
                "team_name": team_name,
                "role_id": str(team_role.id),
                "mock": False,
                "secured": True
            }
        except Exception as e:
            logger.error(f"❌ Failed to create secured Discord channel: {e}")
            return self._create_mock_channel_data(match_id, team_name)

    def _create_mock_channel_data(self, match_id: str, team_name: str) -> Dict[str, Any]:
        """Create mock channel data for development."""
        mock_channel_id = f"mock_{match_id}_{team_name.lower().replace(' ', '_')}"
        return {
            "channel_id": mock_channel_id,
            "channel_name": f"LoL Match {match_id} - {team_name}",
            "invite_url": f"https://discord.gg/mock-invite-{mock_channel_id}",
            "match_id": match_id,
            "team_name": team_name,
            "role_id": f"mock_role_{mock_channel_id}",
            "mock": True,
            "secured": False,
            "note": "Это тестовые данные. Для реальных Discord каналов установите Discord и настройте бота."
        }

    async def create_team_channels(
        self,
        match_id: str,
        blue_team: List[str],
        red_team: List[str]
    ) -> Dict[str, Any]:
        """Create secured channels for both teams with role-based access."""
        logger.info(f"🎮 Creating secured team channels for match {match_id}")

        blue_channel = await self.create_voice_channel(match_id, "Blue Team")
        await asyncio.sleep(0.5)
        red_channel = await self.create_voice_channel(match_id, "Red Team")

        result = {
            "match_id": match_id,
            "blue_team": blue_channel,
            "red_team": red_channel,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "mock_mode": self.mock_mode,
            "secured": not self.mock_mode
        }
        if self.mock_mode:
            result["note"] = "Режим разработки: используются тестовые данные Discord"
        else:
            result["note"] = "Каналы защищены: игроки имеют доступ только к каналам своей команды"
        return result

    async def assign_player_to_team(self, discord_user_id: int, match_id: str, team_name: str) -> bool:
        """Assign a Discord user to a team role and save match info."""
        if self.mock_mode:
            logger.info(f"🎮 MOCK: Assigning user {discord_user_id} to {team_name} in match {match_id}")
            return True
            
        if not self.connected or not self.guild:
            logger.warning("Discord not connected - cannot assign role")
            return False
            
        try:
            # Find team role
            role_name = f"LoL {match_id} - {team_name}"
            team_role = None
            
            for role in self.guild.roles:
                if role.name == role_name:
                    team_role = role
                    break
                    
            if not team_role:
                logger.error(f"Team role not found: {role_name}")
                return False

            # Find member
            member = self.guild.get_member(discord_user_id)
            if not member:
                logger.error(f"Discord user {discord_user_id} not found in guild")
                return False

            # Assign role
            await member.add_roles(team_role, reason=f"Assigned to {team_name} in match {match_id}")
            logger.info(f"✅ Assigned {member.display_name} to role {team_role.name}")

            # Сохраняем информацию о матче для автоматического перемещения
            user_key = f"user_discord:{discord_user_id}"
            match_info = {
                'match_id': match_id,
                'team_name': team_name,
                'assigned_at': datetime.now(timezone.utc).isoformat()
            }
            redis_manager.redis.setex(user_key, 3600, json.dumps(match_info))  # Храним 1 час
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to assign player to team: {e}")
            return False

    async def cleanup_team_roles(self, match_id: str):
        """Cleanup roles after match ends."""
        if not self.connected or not self.guild:
            return
        try:
            roles_to_delete = []
            for role in self.guild.roles:
                if f"LoL {match_id} -" in role.name:
                    roles_to_delete.append(role)
            for role in roles_to_delete:
                try:
                    await role.delete(reason=f"LoL match {match_id} ended")
                    logger.info(f"✅ Deleted role: {role.name}")
                except Exception as e:
                    logger.error(f"❌ Failed to delete role {role.name}: {e}")
        except Exception as e:
            logger.error(f"❌ Error during role cleanup: {e}")

    async def cleanup_match_channels(self, match_data: Dict[str, Any]):
        """Cleanup channels and roles after match ends."""
        if self.mock_mode:
            logger.info(f"🎮 MOCK: Cleaning up channels for match {match_data.get('match_id')}")
            return
        try:
            tasks = []
            if 'blue_team' in match_data and not match_data['blue_team'].get('mock', True):
                channel_id = int(match_data['blue_team']['channel_id'])
                tasks.append(self.delete_voice_channel(channel_id))
            if 'red_team' in match_data and not match_data['red_team'].get('mock', True):
                channel_id = int(match_data['red_team']['channel_id'])
                tasks.append(self.delete_voice_channel(channel_id))
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            # Cleanup roles
            match_id = match_data.get('match_id')
            if match_id:
                await self.cleanup_team_roles(match_id)
            logger.info(f"✅ Cleaned up secured channels and roles for match {match_data['match_id']}")
        except Exception as e:
            logger.error(f"❌ Failed to cleanup match channels and roles: {e}")

    async def disconnect_all_members(self, channel_id: int):
        """Disconnect all members from a voice channel."""
        if self.mock_mode or not self.client:
            return
        try:
            channel = self.client.get_channel(channel_id)
            if isinstance(channel, VoiceChannel):
                members = channel.members
                if members:
                    logger.info(f"🔌 Disconnecting {len(members)} members from channel {channel.name}")
                    for member in members:
                        try:
                            await member.move_to(None)  # Отключаем пользователя
                            logger.debug(f"✅ Disconnected {member.display_name} from voice channel")
                        except Exception as e:
                            logger.warning(f"⚠️ Failed to disconnect {member.display_name}: {e}")
                    logger.info(f"✅ Successfully disconnected all members from {channel.name}")
                else:
                    logger.info(f"🔍 No members in channel {channel.name} to disconnect")
        except Exception as e:
            logger.error(f"❌ Failed to disconnect members from channel {channel_id}: {e}")

    async def delete_voice_channel(self, channel_id: int):
        """Delete a voice channel by ID, first disconnecting all members."""
        if self.mock_mode or not self.client:
            return
        try:
            channel = self.client.get_channel(channel_id)
            if isinstance(channel, VoiceChannel):
                # Сначала отключаем всех участников
                await self.disconnect_all_members(channel_id)
                # Затем удаляем канал
                await channel.delete(reason="LoL match ended")
                logger.info(f"✅ Deleted Discord voice channel: {channel.name} (ID: {channel_id})")
        except discord.NotFound:
            logger.warning(f"⚠️ Channel {channel_id} not found (already deleted)")
        except Exception as e:
            logger.error(f"❌ Failed to delete Discord channel {channel_id}: {e}")

    async def force_disconnect_all_matches(self):
        """Force disconnect all members from all LoL voice channels (emergency cleanup)."""
        if self.mock_mode or not self.guild or not self.category:
            logger.info("🎮 MOCK: Force disconnect all matches")
            return {"disconnected_members": 0, "channels_processed": 0}
        
        try:
            disconnected_count = 0
            channel_count = 0
            
            for channel in self.category.voice_channels:
                if "LoL Match" in channel.name and isinstance(channel, VoiceChannel):
                    channel_count += 1
                    members = channel.members
                    if members:
                        logger.info(f"🔌 Force disconnecting {len(members)} members from {channel.name}")
                        for member in members:
                            try:
                                await member.move_to(None)
                                disconnected_count += 1
                            except Exception as e:
                                logger.warning(f"⚠️ Failed to force disconnect {member.display_name}: {e}")
            
            logger.info(f"✅ Force disconnected {disconnected_count} members from {channel_count} LoL channels")
            return {
                "disconnected_members": disconnected_count,
                "channels_processed": channel_count
            }
        except Exception as e:
            logger.error(f"❌ Failed to force disconnect all matches: {e}")
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
            logger.info("✅ Discord service disconnected")
        except Exception as e:
            logger.error(f"Error during Discord disconnect: {e}")

    def get_status(self) -> Dict[str, Any]:
        """Get Discord service status."""
        return {
            "connected": self.connected,
            "mock_mode": self.mock_mode,
            "guild_available": self.guild is not None,
            "category_available": self.category is not None,
            "status": "mock" if self.mock_mode else "connected" if self.connected else "disconnected"
        }


# Global instance
discord_service = DiscordService()
