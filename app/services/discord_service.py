import discord
from discord import Guild, VoiceChannel
from typing import List, Optional, Dict, Any
import logging
from app.config import settings
from app.utils.exceptions import DiscordServiceException

logger = logging.getLogger(__name__)

class DiscordService:
    def __init__(self):
        self.client = None
        self.guild = None
        self.connected = False
        self.category_name = "LoL Voice Chat"
        self.category = None
        
    async def connect(self):
        """Connect to Discord"""
        try:
            if not settings.DISCORD_BOT_TOKEN:
                logger.warning("DISCORD_BOT_TOKEN not set, Discord integration disabled")
                return False
                
            intents = discord.Intents.default()
            intents.members = True
            intents.voice_states = True
            intents.presences = True
            
            self.client = discord.Client(intents=intents)
            
            @self.client.event
            async def on_ready():
                logger.info(f'✅ Discord bot connected as {self.client.user}')
                self.connected = True
                
                # Find the specific guild if ID provided, otherwise use first guild
                if settings.DISCORD_GUILD_ID:
                    self.guild = self.client.get_guild(int(settings.DISCORD_GUILD_ID))
                    if not self.guild:
                        logger.error(f"Guild with ID {settings.DISCORD_GUILD_ID} not found")
                        return
                else:
                    self.guild = self.client.guilds[0] if self.client.guilds else None
                
                if not self.guild:
                    logger.error("No guilds available for the bot")
                    return
                    
                logger.info(f'✅ Connected to guild: {self.guild.name}')
                
                # Find or create category
                self.category = await self.get_or_create_category()
                logger.info(f'✅ Using category: {self.category.name}')
                
            await self.client.start(settings.DISCORD_BOT_TOKEN)
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to Discord: {e}")
            return False
    
    async def get_or_create_category(self) -> discord.CategoryChannel:
        """Get or create voice chat category"""
        # Check existing categories
        for category in self.guild.categories:
            if category.name == self.category_name:
                logger.info(f'Found existing category: {category.name}')
                return category
        
        # Create new category
        logger.info(f'Creating new category: {self.category_name}')
        return await self.guild.create_category(self.category_name)
    
    async def create_voice_channel(self, match_id: str, team_name: str) -> Dict[str, Any]:
        """Create a voice channel for a team"""
        try:
            channel_name = f"LoL Match {match_id} - {team_name}"
            
            logger.info(f'Creating voice channel: {channel_name}')
            
            # Create voice channel
            voice_channel = await self.guild.create_voice_channel(
                name=channel_name,
                category=self.category,
                reason=f"Voice chat for LoL match {match_id}"
            )
            
            # Create invite link
            invite = await voice_channel.create_invite(max_uses=10, unique=True, reason="Auto-generated for LoL match")
            
            logger.info(f'✅ Voice channel created: {voice_channel.name}')
            
            return {
                "channel_id": str(voice_channel.id),
                "channel_name": channel_name,
                "invite_url": invite.url,
                "match_id": match_id,
                "team_name": team_name
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to create voice channel: {e}")
            raise DiscordServiceException(f"Failed to create voice channel: {e}")
    
    async def create_team_channels(self, match_id: str, blue_team: List[str], red_team: List[str]) -> Dict[str, Any]:
        """Create voice channels for both teams"""
        try:
            blue_channel = await self.create_voice_channel(match_id, "Blue Team")
            red_channel = await self.create_voice_channel(match_id, "Red Team")
            
            return {
                "match_id": match_id,
                "blue_team": blue_channel,
                "red_team": red_channel,
                "created_at": discord.utils.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to create team channels: {e}")
            raise DiscordServiceException(f"Failed to create team channels: {e}")
    
    async def delete_voice_channel(self, channel_id: int):
        """Delete a voice channel"""
        try:
            channel = self.client.get_channel(channel_id)
            if channel:
                await channel.delete(reason="LoL match ended")
                logger.info(f'✅ Deleted voice channel {channel_id}')
        except Exception as e:
            logger.error(f"❌ Failed to delete voice channel {channel_id}: {e}")
    
    async def cleanup_match_channels(self, match_data: Dict[str, Any]):
        """Cleanup channels after match ends"""
        try:
            if 'blue_team' in match_data:
                await self.delete_voice_channel(int(match_data['blue_team']['channel_id']))
            if 'red_team' in match_data:
                await self.delete_voice_channel(int(match_data['red_team']['channel_id']))
        except Exception as e:
            logger.error(f"❌ Failed to cleanup match channels: {e}")

# Global instance
discord_service = DiscordService()
