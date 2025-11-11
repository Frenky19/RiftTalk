from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse
from contextlib import asynccontextmanager
import logging
import os
from datetime import datetime, timezone

from app.config import settings
from app.database import redis_manager
from app.services.lcu_service import lcu_service
from app.services.discord_service import discord_service
from app.services.voice_service import voice_service
from app.endpoints import voice, auth, lcu

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan with proper cleanup."""
    logger.info("🚀 Starting LoL Voice Chat API...")
    await initialize_services()
    yield
    logger.info("🛑 Shutting down...")
    await cleanup_services()


async def initialize_services():
    """Initialize all services with proper error handling."""
    logger.info("🚀 Initializing services...")
    # Discord service - always True
    discord_status = "disabled"
    if settings.DISCORD_BOT_TOKEN:
        try:
            discord_initialized = await discord_service.connect()
            if discord_initialized:
                if discord_service.connected:
                    discord_status = "connected"
                    logger.info("✅ Discord service: CONNECTED")
                else:
                    discord_status = "mock_mode"
                    logger.info("🔶 Discord service: MOCK MODE (Discord not available)")
            else:
                discord_status = "failed"
                logger.warning("⚠️ Discord service: FAILED")
        except Exception as e:
            discord_status = f"error: {e}"
            logger.error(f"❌ Discord service: ERROR - {e}")
    else:
        logger.info("🔶 Discord service: DISABLED (no token)")
    # LCU service - always True
    lcu_status = "disconnected"
    try:
        lcu_initialized = await lcu_service.initialize()
        if lcu_initialized and lcu_service.lcu_connector.is_connected():
            lcu_status = "connected"
            await lcu_service.start_monitoring(handle_game_event)
            logger.info("✅ LCU service: CONNECTED and monitoring")
        else:
            lcu_status = "disconnected"
            logger.info("🔶 LCU service: DISCONNECTED (game not running)")
    except Exception as e:
        lcu_status = f"error: {e}"
        logger.warning(f"⚠️ LCU service: WARNING - {e}")
    # Redis service
    redis_status = "connected"
    try:
        if redis_manager.redis.ping():
            logger.info("✅ Redis service: CONNECTED")
        else:
            redis_status = "error"
            logger.error("❌ Redis service: ERROR")
    except Exception as e:
        redis_status = f"error: {e}"
        logger.error(f"❌ Redis service: ERROR - {e}")

    logger.info("🎮 All services initialized!")
    logger.info(f"📊 Status: Redis={redis_status}, Discord={discord_status}, LCU={lcu_status}")


async def cleanup_services():
    """Cleanup all services."""
    try:
        await lcu_service.cleanup()
    except Exception as e:
        logger.error(f"LCU cleanup error: {e}")
    try:
        await discord_service.disconnect()
    except Exception as e:
        logger.error(f"Discord cleanup error: {e}")


async def handle_game_event(event_type: str, data: dict):
    """Handle game events from LCU."""
    try:
        logger.info(f"Game event: {event_type}")
        if event_type == "match_start":
            match_id = data.get('match_id')
            if match_id:
                await voice_service.create_voice_room(
                    match_id,
                    data.get('players', []),
                    {
                        'blue_team': data.get('blue_team', []),
                        'red_team': data.get('red_team', [])
                    }
                )
        elif event_type == "match_end":
            match_id = data.get('match_id')
            if match_id:
                await voice_service.close_voice_room(match_id)
    except Exception as e:
        logger.error(f"Error handling game event: {e}")

# Create FastAPI app
app = FastAPI(
    title="LoL Voice Chat API",
    description="Discord voice chat integration for League of Legends",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files
static_dir = "static"
if os.path.exists(static_dir):
    try:
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

        @app.get("/demo")
        async def demo_page():
            """Serve demo page for testing."""
            demo_file = os.path.join(static_dir, "demo.html")
            if os.path.exists(demo_file):
                return FileResponse(demo_file)
            raise HTTPException(status_code=404, detail="Demo file not found")
        logger.info(f"✅ Static files mounted from {static_dir}")
    except Exception as e:
        logger.error(f"❌ Failed to mount static files: {e}")
else:
    logger.warning(f"⚠️ Static directory '{static_dir}' not found")

# Include routers
app.include_router(voice.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(lcu.router, prefix="/api")


@app.get("/")
async def root():
    return {
        "message": "LoL Voice Chat API is running! 🎮",
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.get("/health")
async def health_check():
    """Comprehensive health check."""
    services = {
        "api": "healthy",
        "redis": "checking...",
        "discord": "checking...",
        "lcu": "checking..."
    }

    # Redis health
    try:
        if redis_manager.redis.ping():
            services["redis"] = "healthy"
        else:
            services["redis"] = "unhealthy"
    except Exception as e:
        services["redis"] = f"error: {str(e)}"

    # Discord health
    discord_status = discord_service.get_status()
    if not settings.DISCORD_BOT_TOKEN:
        services["discord"] = "disabled"
    elif discord_status["connected"]:
        services["discord"] = "connected"
    elif discord_status["mock_mode"]:
        services["discord"] = "mock_mode"
    else:
        services["discord"] = "disconnected"

    # LCU health
    try:
        lcu_health = await lcu_service.health_check()
        services["lcu"] = "connected" if lcu_health.get("connected") else "disconnected"
    except:
        services["lcu"] = "unavailable"
    return JSONResponse(content={
        "status": "healthy",
        "services": services,
        "discord_details": discord_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "message": "Приложение работает! Discord в режиме заглушки - установите Discord для полноценной работы."
    })


@app.exception_handler(500)
async def internal_server_error_handler(request, exc):
    """Handle internal server errors."""
    logger.error(f"Internal server error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.SERVER_HOST,
        port=settings.SERVER_PORT,
        reload=settings.DEBUG
    )
