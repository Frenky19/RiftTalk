from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings configuration using pydantic-settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )
    # Server Configuration
    SERVER_HOST: str = Field(default="0.0.0.0")
    SERVER_PORT: int = Field(default=8000)
    # Redis Configuration (без пароля)
    REDIS_URL: str = Field(default="redis://localhost:6379")
    REDIS_SSL: bool = Field(default=False)
    REDIS_MAX_CONNECTIONS: int = Field(default=20)
    # JWT Configuration
    JWT_SECRET_KEY: str = Field(...)
    JWT_ALGORITHM: str = Field(default="HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30)
    # LCU API Configuration
    LCU_UPDATE_INTERVAL: int = Field(default=5)
    # Application Configuration
    DEBUG: bool = Field(default=False)
    ENVIRONMENT: str = Field(default="development")
    # Discord Integration
    DISCORD_BOT_TOKEN: Optional[str] = Field(default=None)
    DISCORD_GUILD_ID: Optional[str] = Field(default=None)
    DISCORD_AUTO_CREATE_CHANNELS: bool = Field(default=True)

    def __init__(self, **kwargs):
        """Initialize settings with validation."""
        super().__init__(**kwargs)
        self._validate_required_settings()

    def _validate_required_settings(self):
        """Validate required settings."""
        if not self.JWT_SECRET_KEY or self.JWT_SECRET_KEY.startswith("your-"):
            raise ValueError(
                "JWT_SECRET_KEY must be set and not use default value"
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
    def discord_enabled(self) -> bool:
        """Check if Discord integration is enabled."""
        return bool(self.DISCORD_BOT_TOKEN and self.DISCORD_GUILD_ID)


# Global settings instance
try:
    settings = Settings()
except Exception as e:
    print(f"❌ Failed to load settings: {e}")
    print("💡 Please check your .env file configuration")
    raise
