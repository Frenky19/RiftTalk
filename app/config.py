import os
import sys
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
import platform

# Для работы в .exe
if getattr(sys, 'frozen', False):
    # Если запущено как .exe
    base_dir = os.path.dirname(sys.executable)
else:
    # Если запущено как скрипт
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Обновляем пути
os.chdir(base_dir)


class Settings(BaseSettings):
    """Application settings configuration optimized for Windows local setup."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )
    
    # Server Configuration
    SERVER_HOST: str = Field(default="0.0.0.0")
    SERVER_PORT: int = Field(default=8000)
    
    # Redis Configuration
    REDIS_URL: str = Field(default="redis://localhost:6379")
    REDIS_SSL: bool = Field(default=False)
    REDIS_MAX_CONNECTIONS: int = Field(default=20)
    
    # JWT Configuration
    JWT_SECRET_KEY: str = Field(default="your-super-secret-jwt-key-change-this-in-production")
    JWT_ALGORITHM: str = Field(default="HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30)
    
    # LCU API Configuration
    LCU_UPDATE_INTERVAL: int = Field(default=5)
    
    # Application Configuration
    DEBUG: bool = Field(default=False)
    ENVIRONMENT: str = Field(default="development")
    DOCKER_CONTAINER: bool = Field(default=False)  # False for local Windows
    
    # Discord Integration
    DISCORD_BOT_TOKEN: Optional[str] = Field(default=None)
    DISCORD_GUILD_ID: Optional[str] = Field(default=None)
    DISCORD_AUTO_CREATE_CHANNELS: bool = Field(default=True)

    # Demo Page Authentication
    DEMO_USERNAME: str = Field(default="admin")
    DEMO_PASSWORD: str = Field(default="password")
    DEMO_AUTH_ENABLED: bool = Field(default=True)

    def __init__(self, **kwargs):
        """Initialize settings with validation."""
        super().__init__(**kwargs)
        self._validate_required_settings()

    def _validate_required_settings(self):
        """Validate required settings."""
        if not self.JWT_SECRET_KEY or self.JWT_SECRET_KEY.startswith("your-"):
            raise ValueError(
                "JWT_SECRET_KEY must be set and not use default value. "
                "Update your .env file with a secure secret key."
            )
        if self.DISCORD_BOT_TOKEN and not self.DISCORD_GUILD_ID:
            raise ValueError(
                "DISCORD_GUILD_ID is required when DISCORD_BOT_TOKEN is set"
            )

    @property
    def is_development(self) -> bool:
        """Check if environment is development."""
        return self.ENVIRONMENT.lower() == "development"

    @property
    def is_production(self) -> bool:
        """Check if environment is production."""
        return self.ENVIRONMENT.lower() == "production"

    @property
    def is_windows(self) -> bool:
        """Check if running on Windows."""
        return platform.system().lower() == "windows"

    @property
    def discord_enabled(self) -> bool:
        """Check if Discord integration is enabled."""
        return bool(self.DISCORD_BOT_TOKEN and self.DISCORD_GUILD_ID)


# Global settings instance
try:
    settings = Settings()
    if settings.is_windows:
        print("✅ Running on Windows - LCU integration enabled")
    else:
        print("⚠️  Running on non-Windows system - LCU may have limited functionality")
except Exception as e:
    print(f"❌ Failed to load settings: {e}")
    print("💡 Please check your .env file configuration")
    raise
