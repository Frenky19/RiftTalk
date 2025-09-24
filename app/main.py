from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from contextlib import asynccontextmanager
import asyncio
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
    """Application lifespan context manager."""
    # Startup
    logger.info("Starting up LoL Voice Chat API...")
    # Initialize Discord service
    discord_initialized = False
    try:
        if settings.DISCORD_BOT_TOKEN:
            discord_initialized = await discord_service.connect()
            if discord_initialized:
                logger.info("✅ Discord service initialized successfully")
            else:
                logger.warning("⚠️ Discord service not available")
        else:
            logger.info("🔧 Discord integration disabled (no token provided)")
    except Exception as e:
        logger.error(f"❌ Discord service failed: {e}")
    # Initialize LCU service (optional)
    lcu_initialized = False
    try:
        lcu_initialized = await lcu_service.initialize()
        if lcu_initialized:
            asyncio.create_task(
                lcu_service.start_monitoring(handle_game_event)
            )
            logger.info("✅ LCU service initialized successfully")
        else:
            logger.info("🔧 LCU service not available")
    except Exception as e:
        logger.warning(f"⚠️ LCU service failed: {e}")
    yield
    # Shutdown
    logger.info("Shutting down...")
    try:
        if discord_initialized:
            await discord_service.disconnect()
            logger.info("✅ Discord service disconnected")
        if lcu_initialized:
            await lcu_service.stop_monitoring()
            logger.info("✅ LCU service stopped")
    except Exception as e:
        logger.error(f"❌ Error during shutdown: {e}")


async def handle_game_event(event_type: str, data: dict):
    """Handle game events from LCU."""
    try:
        if event_type == "match_start":
            match_id = data.get('match_id', 'unknown')
            logger.info(f"🎮 Match started: {match_id}")
            # Здесь можно автоматически создавать Discord каналы
        elif event_type == "match_end":
            match_id = data.get('match_id', 'unknown')
            logger.info(f"🎮 Match ended: {match_id}")
            # Автоматически закрывать комнаты
            try:
                await voice_service.close_voice_room(match_id)
                logger.info(f"✅ Voice room closed for match: {match_id}")
            except Exception as e:
                logger.error(f"❌ Error closing voice room: {e}")
    except Exception as e:
        logger.error(f"❌ Error handling game event: {e}")


# Create FastAPI app
app = FastAPI(
    title="LoL Voice Chat API",
    description="Discord voice chat integration for League of Legends",
    version="1.0.0",
    lifespan=lifespan
)


# Serve static files with error handling
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


# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this!
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Include routers
app.include_router(voice.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(lcu.router, prefix="/api")


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "message": "LoL Voice Chat API with Discord integration is running! 🎮",
        "docs": "/docs",
        "health": "/health",
        "demo": "/demo" if os.path.exists(static_dir) else None
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    redis_status = "unknown"
    try:
        redis_status = "healthy" if redis_manager.redis.ping() else "unhealthy"
    except Exception as e:
        redis_status = f"unhealthy: {str(e)}"
    discord_status = "enabled" if settings.DISCORD_BOT_TOKEN else "disabled"
    return JSONResponse(
        content={
            "status": "healthy",
            "redis": redis_status,
            "discord": discord_status,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    )


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
        app,
        host=settings.SERVER_HOST,
        port=settings.SERVER_PORT,
        log_level="info"
    )
