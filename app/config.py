import os
from dotenv import load_dotenv
from pydantic import BaseSettings

load_dotenv()


class Settings(BaseSettings):
    # Server
    SERVER_HOST: str = os.getenv("SERVER_HOST", "0.0.0.0")
    SERVER_PORT: int = int(os.getenv("SERVER_PORT", 8000))
    # Redis
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379")
    REDIS_PASSWORD: str = os.getenv("REDIS_PASSWORD", "")
    # JWT
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "your-secret-key")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
        os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30)
    )
    # WebRTC
    TURN_SERVER_URL: str = os.getenv("TURN_SERVER_URL", "")
    TURN_SERVER_USERNAME: str = os.getenv("TURN_SERVER_USERNAME", "")
    TURN_SERVER_PASSWORD: str = os.getenv("TURN_SERVER_PASSWORD", "")
    # LCU API
    LCU_UPDATE_INTERVAL: int = int(os.getenv("LCU_UPDATE_INTERVAL", 5))

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
