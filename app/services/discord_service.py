import asyncio
import discord
import logging
import json
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from discord import Guild, VoiceChannel, CategoryChannel, Role
from app.config import settings
try:
    from app.database import redis_manager
except Exception as e:
    # Fallback для случаев когда Redis недоступен
    import logging
    logger = logging.getLogger(__name__)
    logger.warning(f"Redis not available, using memory storage: {e}")
    
    # Создаем простой fallback
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
                        logger.info(f"✅ Connected to guild: {self.guild.name} (ID: {self.guild.id})")
                        logger.info(f"👥 Guild member count: {self.guild.member_count}")
                    else:
                        logger.warning(f"⚠️ Guild with ID {settings.DISCORD_GUILD_ID} not found in bot's guilds")
                        # List available guilds for debugging
                        available_guilds = [f"{g.name} (ID: {g.id})" for g in self.client.guilds]
                        logger.info(f"📋 Bot is in these guilds: {available_guilds}")
                        self.mock_mode = True
                        return
                except ValueError:
                    logger.error(f"❌ Invalid DISCORD_GUILD_ID format: {settings.DISCORD_GUILD_ID}")
                    self.mock_mode = True
                    return
            else:
                if self.client.guilds:
                    self.guild = self.client.guilds[0]
                    logger.info(f"✅ Using first available guild: {self.guild.name} (ID: {self.guild.id})")
                else:
                    logger.warning("⚠️ Bot is not in any guilds")
                    self.mock_mode = True
                    return

            # Test member fetching capability
            try:
                # Try to fetch the bot itself as a test
                bot_member = self.guild.get_member(self.client.user.id)
                if bot_member:
                    logger.info(f"✅ Bot member found: {bot_member.display_name}")
                else:
                    logger.warning("⚠️ Could not find bot member in guild - possible permissions issue")
                    
                # Check bot permissions
                bot_permissions = self.guild.me.guild_permissions
                required_permissions = [
                    'manage_roles', 'manage_channels', 'view_channel', 
                    'connect', 'speak', 'move_members'
                ]
                
                missing_permissions = []
                for perm in required_permissions:
                    if not getattr(bot_permissions, perm):
                        missing_permissions.append(perm)
                        
                if missing_permissions:
                    logger.warning(f"⚠️ Bot missing permissions: {', '.join(missing_permissions)}")
                else:
                    logger.info("✅ Bot has all required permissions")
                    
            except Exception as e:
                logger.error(f"❌ Error checking bot permissions: {e}")

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
        """Assign a Discord user to a team with enhanced user discovery."""
        if self.mock_mode:
            logger.info(f"🎮 MOCK: Assigning user {discord_user_id} to {team_name} in match {match_id}")
            return True
            
        if not self.connected or not self.guild:
            logger.warning("Discord not connected - cannot assign user to team")
            return False
            
        try:
            logger.info(f"🔍 Searching for user {discord_user_id} in guild {self.guild.name} (ID: {self.guild.id})")
            
            # Multiple methods to find member
            member = None
            
            # Method 1: Check cache first
            member = self.guild.get_member(discord_user_id)
            if member:
                logger.info(f"✅ Found user {member.display_name} in guild cache")
            
            # Method 2: Fetch from API if not in cache
            if not member:
                try:
                    logger.info(f"🔄 Fetching user {discord_user_id} from Discord API...")
                    member = await self.guild.fetch_member(discord_user_id)
                    if member:
                        logger.info(f"✅ Fetched user {member.display_name} from Discord API")
                except discord.NotFound:
                    logger.error(f"❌ Discord user {discord_user_id} not found in guild {self.guild.name}")
                    # Create an invite for the user to join the server
                    await self._create_server_invite_for_user(match_id, team_name, discord_user_id)
                    return False
                except discord.Forbidden:
                    logger.error(f"❌ Bot doesn't have permission to fetch member {discord_user_id}")
                    logger.error("💡 Check if bot has 'Server Members Intent' enabled in Discord Developer Portal")
                    return False
                except discord.HTTPException as e:
                    logger.error(f"❌ Discord API error fetching member: {e}")
                    return False

            if not member:
                logger.error(f"❌ Could not find Discord user {discord_user_id} in guild {self.guild.name}")
                logger.info(f"📊 Guild members in cache: {len(self.guild.members)}")
                
                # Try one more method - search in members list
                for guild_member in self.guild.members:
                    if guild_member.id == discord_user_id:
                        member = guild_member
                        logger.info(f"✅ Found user {member.display_name} in members list iteration")
                        break
                
                if not member:
                    logger.error(f"❌ User {discord_user_id} not found in any member list")
                    await self._create_server_invite_for_user(match_id, team_name, discord_user_id)
                    return False

            # Find team role
            role_name = f"LoL {match_id} - {team_name}"
            team_role = None
            
            logger.info(f"🔍 Searching for role: {role_name}")
            for role in self.guild.roles:
                if role.name == role_name:
                    team_role = role
                    logger.info(f"✅ Found team role: {role.name} (ID: {role.id})")
                    break
                    
            if not team_role:
                logger.error(f"❌ Team role not found: {role_name}")
                # Try to create the role
                team_role = await self._get_or_create_team_role(match_id, team_name)
                if not team_role:
                    logger.error("❌ Failed to create team role")
                    return False

            # Check if bot has permission to manage roles
            if not self.guild.me.guild_permissions.manage_roles:
                logger.error("❌ Bot doesn't have 'Manage Roles' permission")
                return False

            # Check if bot's role is high enough to assign this role
            if self.guild.me.top_role <= team_role:
                logger.error(f"❌ Bot's role ({self.guild.me.top_role.name}) is not high enough to assign role {role_name}")
                logger.error("💡 Move bot's role higher in role hierarchy")
                return False

            # Check if member already has the role
            if team_role in member.roles:
                logger.info(f"ℹ️ User {member.display_name} already has role {team_role.name}")
                return True

            # Assign role
            try:
                await member.add_roles(team_role, reason=f"Assigned to {team_name} in match {match_id}")
                logger.info(f"✅ Assigned {member.display_name} to role {team_role.name}")

                # Save match info for automatic voice channel management
                user_key = f"user_discord:{discord_user_id}"
                match_info = {
                    'match_id': match_id,
                    'team_name': team_name,
                    'assigned_at': datetime.now(timezone.utc).isoformat()
                }
                redis_manager.redis.setex(user_key, 3600, json.dumps(match_info))
                
                return True
                
            except discord.Forbidden:
                logger.error(f"❌ No permission to assign role to {member.display_name}")
                logger.error("💡 Check role hierarchy and bot permissions")
                return False
            except discord.HTTPException as e:
                logger.error(f"❌ Failed to assign role: {e}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Failed to assign player to team: {e}")
            return False

    async def _create_server_invite_for_user(self, match_id: str, team_name: str, discord_user_id: int):
        """Create a server invite and notify about the need to join the server."""
        try:
            if not self.guild:
                return
                
            # Create an invite for the user
            invite_channel = self.guild.system_channel or next(
                (ch for ch in self.guild.text_channels if ch.permissions_for(self.guild.me).create_instant_invite), None)
            
            if invite_channel:
                invite = await invite_channel.create_invite(
                    max_uses=1,
                    unique=True,
                    reason=f"Invite for LoL match {match_id} - {team_name}"
                )
                
                logger.info(f"🔗 Created server invite for user {discord_user_id}: {invite.url}")
                
                # Store the invite for the user
                invite_key = f"server_invite:{discord_user_id}"
                redis_manager.redis.setex(invite_key, 3600, invite.url)
                
                # You could also send a DM to the user if possible
                await self._send_dm_to_user(discord_user_id, invite.url, match_id, team_name)
                
        except Exception as e:
            logger.error(f"❌ Failed to create server invite: {e}")

    async def _send_dm_to_user(self, discord_user_id: int, invite_url: str, match_id: str, team_name: str):
        """Send a direct message to the user with server invite."""
        try:
            if not self.guild:
                return
                
            member = self.guild.get_member(discord_user_id)
            if not member:
                # Try to fetch member
                try:
                    member = await self.guild.fetch_member(discord_user_id)
                except:
                    return
            
            if member:
                embed = discord.Embed(
                    title="🎮 Присоединяйтесь к серверу для голосового чата",
                    description=f"Для участия в голосовом чате матча **{match_id}** в команде **{team_name}**, пожалуйста, присоединитесь к нашему Discord серверу:",
                    color=0x7289da
                )
                embed.add_field(name="Ссылка для присоединения", value=invite_url, inline=False)
                embed.add_field(name="Инструкция", value="1. Нажмите на ссылку выше\n2. Присоединитесь к серверу\n3. Вернитесь в игру", inline=False)
                embed.set_footer(text="LoL Voice Chat")
                
                await member.send(embed=embed)
                logger.info(f"📨 Sent DM with server invite to {member.display_name}")
                
        except discord.Forbidden:
            logger.warning(f"⚠️ Cannot send DM to user {discord_user_id} (DMs closed)")
        except Exception as e:
            logger.error(f"❌ Failed to send DM: {e}")

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
        """Cleanup channels and roles after match ends with improved error handling."""
        logger.info(f"🧹 Starting cleanup for match: {match_data}")
        
        if self.mock_mode:
            logger.info(f"🎮 MOCK: Cleaning up channels for match {match_data.get('match_id')}")
            return
            
        try:
            tasks = []
            match_id = match_data.get('match_id')
            
            logger.info(f"🔍 Looking for channels to cleanup in match data: {list(match_data.keys())}")
            
            # Cleanup blue team channel
            if 'blue_team' in match_data and match_data['blue_team']:
                blue_team_data = match_data['blue_team']
                # Проверяем, не mock ли это и есть ли channel_id
                if not blue_team_data.get('mock', True) and blue_team_data.get('channel_id'):
                    try:
                        channel_id = int(blue_team_data['channel_id'])
                        tasks.append(self.delete_voice_channel(channel_id))
                        logger.info(f"🔵 Queueing blue team channel cleanup: {channel_id}")
                    except (ValueError, TypeError) as e:
                        logger.error(f"❌ Invalid blue team channel ID: {blue_team_data.get('channel_id')}, error: {e}")
            
            # Cleanup red team channel  
            if 'red_team' in match_data and match_data['red_team']:
                red_team_data = match_data['red_team']
                if not red_team_data.get('mock', True) and red_team_data.get('channel_id'):
                    try:
                        channel_id = int(red_team_data['channel_id'])
                        tasks.append(self.delete_voice_channel(channel_id))
                        logger.info(f"🔴 Queueing red team channel cleanup: {channel_id}")
                    except (ValueError, TypeError) as e:
                        logger.error(f"❌ Invalid red team channel ID: {red_team_data.get('channel_id')}, error: {e}")
            
            # Execute all cleanup tasks
            if tasks:
                logger.info(f"🔄 Executing {len(tasks)} cleanup tasks...")
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Log results
                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        logger.error(f"❌ Cleanup task {i} failed: {result}")
                    else:
                        logger.info(f"✅ Cleanup task {i} completed successfully")
            else:
                logger.info("ℹ️ No channels to cleanup")
                
            # Cleanup roles
            if match_id:
                logger.info(f"👤 Cleaning up roles for match {match_id}")
                await self.cleanup_team_roles(match_id)
            else:
                logger.warning("⚠️ No match ID provided for role cleanup")
                
            logger.info(f"✅ Cleanup completed for match {match_id}")
            
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
