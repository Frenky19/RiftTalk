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
from app.endpoints import voice, auth, lcu, discord

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
    
    # Discord service
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
    
    # LCU service - enhanced initialization
    lcu_status = "disconnected"
    try:
        lcu_initialized = await lcu_service.initialize()
        if lcu_initialized:
            lcu_status = "initialized"
            logger.info("✅ LCU service: INITIALIZED")
            
            # Register event handlers
            lcu_service.register_event_handler("match_start", handle_game_event)
            lcu_service.register_event_handler("match_end", handle_game_event)
            lcu_service.register_event_handler("champ_select", handle_champ_select)
            lcu_service.register_event_handler("ready_check", handle_ready_check)
            
            # Start monitoring
            await lcu_service.start_monitoring()
            logger.info("🎮 LCU service: MONITORING STARTED")
            
            # Get detailed status
            lcu_details = await lcu_service.get_detailed_status()
            if lcu_details.get('connected'):
                lcu_status = "connected"
                logger.info("✅ LCU service: CONNECTED TO GAME CLIENT")
            else:
                logger.info("🔶 LCU service: WAITING FOR GAME CLIENT")
                
        else:
            lcu_status = "failed"
            logger.warning("⚠️ LCU service: INITIALIZATION FAILED")
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
        await lcu_service.stop_monitoring()
    except Exception as e:
        logger.error(f"LCU cleanup error: {e}")
    try:
        await discord_service.disconnect()
    except Exception as e:
        logger.error(f"Discord cleanup error: {e}")


async def handle_game_event(event_data: dict):
    """Handle game events from LCU with enhanced logic."""
    try:
        event_type = event_data.get('phase')
        logger.info(f"🎮 Game event received: {event_type}")
        
        if event_type == "match_start":
            match_data = event_data.get('match_data')
            if match_data:
                match_id = match_data.get('match_id')
                players = match_data.get('players', [])
                
                if match_id and players:
                    logger.info(f"🚀 Creating voice room for match {match_id} with {len(players)} players")
                    try:
                        # Convert player data to the format expected by voice service
                        player_ids = [p.get('summoner_id') for p in players if p.get('summoner_id')]
                        
                        await voice_service.create_voice_room(
                            match_id,
                            player_ids,
                            {
                                'blue_team': match_data.get('blue_team', []),
                                'red_team': match_data.get('red_team', [])
                            }
                        )
                        logger.info(f"✅ Successfully created voice room for match {match_id}")
                    except Exception as e:
                        logger.error(f"❌ Failed to create voice room for match {match_id}: {e}")
                else:
                    logger.warning(f"⚠️ Invalid match data for match_start: {match_data}")
                    
        elif event_type == "match_end":
            match_data = event_data.get('match_data')
            if match_data:
                match_id = match_data.get('match_id')
                if match_id:
                    logger.info(f"🛑 Closing voice room for match {match_id}")
                    try:
                        success = await voice_service.close_voice_room(match_id)
                        if success:
                            logger.info(f"✅ Successfully closed voice room for match {match_id}")
                        else:
                            logger.warning(f"⚠️ No active voice room found for match {match_id}")
                    except Exception as e:
                        logger.error(f"❌ Failed to close voice room for match {match_id}: {e}")
                        
    except Exception as e:
        logger.error(f"❌ Error handling game event: {e}")


async def handle_champ_select(event_data: dict):
    """Handle champion selection phase."""
    try:
        logger.info("🎯 Champion selection started")
        match_data = event_data.get('match_data')
        if match_data:
            logger.info(f"👥 Players in champ select: {len(match_data.get('players', []))}")
            # Here you can add logic for champ select phase
    except Exception as e:
        logger.error(f"❌ Error handling champ select: {e}")


async def handle_ready_check(event_data: dict):
    """Handle ready check phase."""
    try:
        logger.info("✅ Ready check detected")
        # Here you can add logic for ready check phase
    except Exception as e:
        logger.error(f"❌ Error handling ready check: {e}")


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
app.include_router(discord.router, prefix="/api")


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
        lcu_details = await lcu_service.get_detailed_status()
        if lcu_details.get('connected'):
            services["lcu"] = "connected"
        elif lcu_details.get('initialized'):
            services["lcu"] = "waiting_for_game"
        else:
            services["lcu"] = "disconnected"
    except:
        services["lcu"] = "unavailable"
    
    # Правильное сообщение в зависимости от статуса Discord
    if services["discord"] == "connected":
        message = "✅ Приложение работает! Discord подключен и готов к работе."
    elif services["discord"] == "mock_mode":
        message = "🔶 Приложение работает! Discord в режиме заглушки - установите Discord для полноценной работы."
    elif services["discord"] == "disabled":
        message = "🔶 Приложение работает! Discord отключен - настройте DISCORD_BOT_TOKEN для подключения."
    else:
        message = "❌ Приложение работает! Discord не подключен."

    # Добавляем информацию о LCU
    if services["lcu"] == "connected":
        message += " 🎮 LCU подключен к клиенту игры."
    elif services["lcu"] == "waiting_for_game":
        message += " 🔶 LCU ожидает запуск League of Legends."

    return JSONResponse(content={
        "status": "healthy",
        "services": services,
        "discord_details": discord_status,
        "lcu_details": await lcu_service.get_detailed_status(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "message": message
    })


@app.get("/status")
async def quick_status():
    """Quick status check for the demo page."""
    discord_status = discord_service.get_status()
    redis_healthy = False
    try:
        redis_healthy = redis_manager.redis.ping()
    except:
        pass
        
    lcu_details = await lcu_service.get_detailed_status()
    lcu_connected = lcu_details.get('connected', False)
    lcu_monitoring = lcu_details.get('monitoring', False)
    
    return {
        "discord": {
            "connected": discord_status["connected"],
            "mock_mode": discord_status["mock_mode"],
            "status": discord_status["status"]
        },
        "redis": "healthy" if redis_healthy else "unhealthy",
        "lcu": {
            "connected": lcu_connected,
            "monitoring": lcu_monitoring,
            "current_phase": lcu_details.get('current_phase'),
            "status": "connected" if lcu_connected else "disconnected"
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


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