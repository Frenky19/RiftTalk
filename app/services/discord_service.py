import asyncio
import discord
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from discord import Guild, VoiceChannel, CategoryChannel
from app.config import settings

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
        self.mock_mode = False  # Флаг для режима заглушки

    async def connect(self) -> bool:
        """Connect to Discord or fallback to mock mode."""
        try:
            if not settings.DISCORD_BOT_TOKEN:
                logger.info("🔶 Discord bot token not configured - running in MOCK mode")
                self.mock_mode = True
                return True
            logger.info("🔄 Attempting to connect to Discord...")
            intents = discord.Intents.default()
            intents.members = True
            intents.voice_states = True
            self.client = discord.Client(intents=intents)

            @self.client.event
            async def on_ready():
                logger.info(f"✅ Discord bot connected as {self.client.user}")
                self.connected = True
                await self._initialize_guild_and_category()

            @self.client.event
            async def on_disconnect():
                logger.warning("🔌 Discord bot disconnected")
                self.connected = False

            self.connection_task = asyncio.create_task(self._connect_internal())

            await asyncio.sleep(5)

            if not self.connected:
                logger.warning("⚠️ Discord connection timeout - running in MOCK mode")
                logger.info("💡 Для полноценной работы Discord установите Discord и настройте бота")
                self.mock_mode = True
                await self.disconnect()
            return True

        except Exception as e:
            logger.error(f"❌ Discord connection error: {e}")
            logger.info("🔶 Running in MOCK mode due to Discord connection error")
            self.mock_mode = True
            return True

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
            for category in self.guild.categories:
                if category.name == self.category_name:
                    logger.info(f"✅ Found existing category: {category.name}")
                    return category
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

    async def create_voice_channel(self, match_id: str, team_name: str) -> Dict[str, Any]:
        """Create voice channel or return mock data."""
        if self.mock_mode or not self.connected:
            logger.info(f"🎮 MOCK: Creating voice channel for {team_name} in match {match_id}")
            return self._create_mock_channel_data(match_id, team_name)
        try:
            channel_name = f"LoL Match {match_id} - {team_name}"
            voice_channel = await self.guild.create_voice_channel(
                name=channel_name,
                category=self.category,
                reason=f"Voice chat for LoL match {match_id}"
            )
            invite = await voice_channel.create_invite(
                max_uses=10,
                unique=True,
                reason="Auto-generated for LoL match"
            )
            logger.info(f"✅ Created Discord voice channel: {voice_channel.name}")
            return {
                "channel_id": str(voice_channel.id),
                "channel_name": channel_name,
                "invite_url": invite.url,
                "match_id": match_id,
                "team_name": team_name,
                "mock": False
            }
        except Exception as e:
            logger.error(f"❌ Failed to create Discord channel: {e}")
            logger.info("🔄 Falling back to mock data")
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
            "mock": True,
            "note": "Это тестовые данные. Для реальных Discord каналов установите Discord и настройте бота."
        }

    async def create_team_channels(self, match_id: str, blue_team: List[str], red_team: List[str]) -> Dict[str, Any]:
        """Create channels for both teams with mock support."""
        logger.info(f"🎮 Creating team channels for match {match_id}")
        blue_channel = await self.create_voice_channel(match_id, "Blue Team")
        await asyncio.sleep(0.5)
        red_channel = await self.create_voice_channel(match_id, "Red Team")
        result = {
            "match_id": match_id,
            "blue_team": blue_channel,
            "red_team": red_channel,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "mock_mode": self.mock_mode
        }
        if self.mock_mode:
            result["note"] = "Режим разработки: используются тестовые данные Discord"
        return result

    async def cleanup_match_channels(self, match_data: Dict[str, Any]):
        """Cleanup channels after match ends."""
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
                logger.info(f"✅ Cleaned up Discord channels for match {match_data['match_id']}")
        except Exception as e:
            logger.error(f"❌ Failed to cleanup Discord channels: {e}")

    async def delete_voice_channel(self, channel_id: int):
        """Delete a voice channel by ID."""
        if self.mock_mode or not self.client:
            return
        try:
            channel = self.client.get_channel(channel_id)
            if isinstance(channel, VoiceChannel):
                await channel.delete(reason="LoL match ended")
                logger.info(f"✅ Deleted Discord voice channel: {channel_id}")
        except Exception as e:
            logger.error(f"❌ Failed to delete Discord channel {channel_id}: {e}")

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


discord_service = DiscordService()
