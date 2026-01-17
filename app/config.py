import logging
import os
import sys
from typing import Optional

import platform
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


logger = logging.getLogger(__name__)

# For .exe execution
if getattr(sys, 'frozen', False):
    # If running as .exe
    base_dir = os.path.dirname(sys.executable)
else:
    # If running as script
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Update paths
os.chdir(base_dir)


class Settings(BaseSettings):
    """Application settings configuration optimized for Windows local setup."""

    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        case_sensitive=True,
        extra='ignore'
    )

    # Server Configuration
    SERVER_HOST: str = Field(default='127.0.0.1')
    SERVER_PORT: int = Field(default=8000)
    # Redis Configuration
    REDIS_URL: str = Field(default='redis://localhost:6379')
    REDIS_SSL: bool = Field(default=False)
    REDIS_MAX_CONNECTIONS: int = Field(default=20)
    # JWT Configuration
    JWT_SECRET_KEY: str = Field(
        default='your-super-secret-jwt-key-change-this-in-production'
    )
    JWT_ALGORITHM: str = Field(default='HS256')
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30)
    # LCU API Configuration
    LCU_UPDATE_INTERVAL: int = Field(default=5)
    # Application Configuration
    DEBUG: bool = Field(default=False)
    ENVIRONMENT: str = Field(default='development')
    DOCKER_CONTAINER: bool = Field(default=False)  # False for local Windows
    # Discord Integration
    DISCORD_BOT_TOKEN: Optional[str] = Field(default=None)
    DISCORD_GUILD_ID: Optional[str] = Field(default=None)
    DISCORD_AUTO_CREATE_CHANNELS: bool = Field(default=True)

    # Discord OAuth2 (to link Discord account without manual ID)
    DISCORD_OAUTH_CLIENT_ID: Optional[str] = Field(default=None)
    DISCORD_OAUTH_CLIENT_SECRET: Optional[str] = Field(default=None)
    # If not set, defaults to: http://{SERVER_HOST}:{SERVER_PORT}/api/auth/discord/callback
    DISCORD_OAUTH_REDIRECT_URI: Optional[str] = Field(default=None)
    DISCORD_OAUTH_SCOPES: str = Field(default='identify')
    DISCORD_OAUTH_STATE_TTL_SECONDS: int = Field(default=600)
    # Cleanup / Garbage Collection
    CLEANUP_INTERVAL_SECONDS: int = Field(default=60)
    CLEANUP_INACTIVE_GRACE_SECONDS: int = Field(default=120)
    CLEANUP_STALE_EMPTY_ROOM_HOURS: int = Field(default=2)

    # Discord orphan cleanup (helps when using memory:// and app restarts)
    DISCORD_GC_ON_STARTUP: bool = Field(default=True)
    DISCORD_GC_STALE_HOURS: int = Field(default=2)
    DISCORD_GC_MIN_AGE_MINUTES: int = Field(default=10)

    def __init__(self, **kwargs):
        """Initialize settings with validation."""
        super().__init__(**kwargs)
        self._validate_required_settings()

    def _validate_required_settings(self):
        """Validate required settings."""
        if not self.JWT_SECRET_KEY or self.JWT_SECRET_KEY.startswith('your-'):
            raise ValueError(
                'JWT_SECRET_KEY must be set and not use default value. '
                'Update your .env file with a secure secret key.'
            )
        # Discord is required for this application (strict mode)
        if not self.DISCORD_BOT_TOKEN or not self.DISCORD_GUILD_ID:
            raise ValueError(
                'Discord is required. Set DISCORD_BOT_TOKEN '
                'and DISCORD_GUILD_ID in your .env file.'
            )
        try:
            int(self.DISCORD_GUILD_ID)
        except Exception:
            raise ValueError('DISCORD_GUILD_ID must be a numeric guild ID')

    @property
    def is_development(self) -> bool:
        """Check if environment is development."""
        return self.ENVIRONMENT.lower() == 'development'

    @property
    def is_production(self) -> bool:
        """Check if environment is production."""
        return self.ENVIRONMENT.lower() == 'production'

    @property
    def is_windows(self) -> bool:
        """Check if running on Windows."""
        return platform.system().lower() == 'windows'

    @property
    def discord_enabled(self) -> bool:
        """Check if Discord integration is enabled."""
        return bool(self.DISCORD_BOT_TOKEN and self.DISCORD_GUILD_ID)


try:
    settings = Settings()
    if settings.is_windows:
        logger.info('Running on Windows - LCU integration enabled')
    else:
        logger.warning(
            'Running on non-Windows system - '
            'LCU may have limited functionality'
        )
except Exception as e:
    logger.error(f'Failed to load settings: {e}')
    logger.error('Please check your .env file configuration')
    raise
