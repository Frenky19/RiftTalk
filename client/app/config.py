import logging
import os
import platform
import sys
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# Ensure repo root is on sys.path so shared/ is importable
repo_root = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

# For .exe execution
if getattr(sys, 'frozen', False):
    base_dir = os.path.dirname(sys.executable)
else:
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Update paths
os.chdir(base_dir)


class Settings(BaseSettings):
    """Application settings.

    Two modes:
      - client: runs LCU locally and proxies Discord operations to a remote server
      - server: runs the single Discord bot + OAuth and receives events from clients
    """

    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        case_sensitive=True,
        extra='ignore'
    )

    # Local API (client) / Public API (server) bind
    SERVER_HOST: str = Field(default='127.0.0.1')
    SERVER_PORT: int = Field(default=8000)

    # Mode switch
    APP_MODE: str = Field(default='client')  # client | server

    # Remote server base URL (required in client mode), e.g. https://example.com
    REMOTE_SERVER_URL: Optional[str] = Field(default=None)

    # Shared key for client->server API auth (required in both modes)
    RIFT_SHARED_KEY: Optional[str] = Field(default=None)

    # Public base URL of the server (recommended in server mode),
    # e.g. https://your-domain.com
    # If you don't have a domain yet, you can use a tunnel URL for testing.
    PUBLIC_BASE_URL: Optional[str] = Field(default=None)

    # Redis Configuration
    REDIS_URL: str = Field(default='redis://localhost:6379')
    REDIS_SSL: bool = Field(default=False)
    REDIS_MAX_CONNECTIONS: int = Field(default=20)

    # JWT Configuration (used by local client UI/API session)
    JWT_SECRET_KEY: str = Field(
        default='your-super-secret-jwt-key-change-this-in-production'
    )
    JWT_ALGORITHM: str = Field(default='HS256')
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30)

    # LCU API Configuration (client mode)
    LCU_UPDATE_INTERVAL: int = Field(default=5)

    # Application Configuration
    DEBUG: bool = Field(default=False)
    ENVIRONMENT: str = Field(default='development')
    DOCKER_CONTAINER: bool = Field(default=False)

    # Discord Integration (server mode)
    DISCORD_BOT_TOKEN: Optional[str] = Field(default=None)
    DISCORD_GUILD_ID: Optional[str] = Field(default=None)
    DISCORD_AUTO_CREATE_CHANNELS: bool = Field(default=True)

    # Discord OAuth2 (server mode)
    DISCORD_OAUTH_CLIENT_ID: Optional[str] = Field(default=None)
    DISCORD_OAUTH_CLIENT_SECRET: Optional[str] = Field(default=None)
    # If not set, defaults to:
    # {PUBLIC_BASE_URL}/api/public/discord/callback (server mode)
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
        super().__init__(**kwargs)
        self._validate_required_settings()

    def _validate_required_settings(self):
        mode = (self.APP_MODE or 'client').strip().lower()
        if mode not in ('client', 'server'):
            raise ValueError("APP_MODE must be 'client' or 'server'")

        if not self.JWT_SECRET_KEY or str(self.JWT_SECRET_KEY).startswith('your-'):
            raise ValueError(
                'JWT_SECRET_KEY must be set and not use default value. '
                'Update your .env file with a secure secret key.'
            )

        if mode == 'client':
            if not self.REMOTE_SERVER_URL:
                raise ValueError('REMOTE_SERVER_URL is required in client mode')
            if not self.RIFT_SHARED_KEY:
                raise ValueError('RIFT_SHARED_KEY is required in client mode')
            return

        # server mode
        if not self.RIFT_SHARED_KEY:
            raise ValueError('RIFT_SHARED_KEY is required in server mode')
        if not self.DISCORD_BOT_TOKEN or not self.DISCORD_GUILD_ID:
            raise ValueError(
                'Server mode requires DISCORD_BOT_TOKEN and DISCORD_GUILD_ID in .env'
            )
        try:
            int(self.DISCORD_GUILD_ID)
        except Exception:
            raise ValueError('DISCORD_GUILD_ID must be a numeric guild ID')

        if not self.DISCORD_OAUTH_CLIENT_ID or not self.DISCORD_OAUTH_CLIENT_SECRET:
            raise ValueError(
                'Server mode requires DISCORD_OAUTH_CLIENT_ID '
                'and DISCORD_OAUTH_CLIENT_SECRET'
            )

        if not self.DISCORD_OAUTH_REDIRECT_URI and not self.PUBLIC_BASE_URL:
            raise ValueError(
                'Server mode requires DISCORD_OAUTH_REDIRECT_URI or PUBLIC_BASE_URL'
            )

    @property
    def is_windows(self) -> bool:
        return platform.system().lower() == 'windows'

    @property
    def is_client(self) -> bool:
        return (self.APP_MODE or 'client').strip().lower() == 'client'

    @property
    def is_server(self) -> bool:
        return (self.APP_MODE or 'client').strip().lower() == 'server'

    @property
    def discord_enabled(self) -> bool:
        return bool(self.DISCORD_BOT_TOKEN and self.DISCORD_GUILD_ID)

    def public_base_url_resolved(self) -> str:
        if self.PUBLIC_BASE_URL:
            return str(self.PUBLIC_BASE_URL).rstrip('/')
        host = (
            '127.0.0.1'
            if self.SERVER_HOST in ('0.0.0.0', '::')
            else self.SERVER_HOST
        )
        return f'http://{host}:{self.SERVER_PORT}'

    def discord_redirect_uri(self) -> str:
        if self.DISCORD_OAUTH_REDIRECT_URI:
            return str(self.DISCORD_OAUTH_REDIRECT_URI)
        # server-mode default
        return f'{self.public_base_url_resolved()}/api/public/discord/callback'


try:
    settings = Settings()
    if settings.is_windows:
        logger.info('Running on Windows - LCU integration enabled')
    else:
        logger.warning(
            'Running on non-Windows system - LCU may have limited functionality'
        )
except Exception as e:
    logger.error(f'Failed to load settings: {e}')
    logger.error('Please check your .env file configuration')
    raise
