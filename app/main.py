from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse
from contextlib import asynccontextmanager
import logging
import os
import json
from datetime import datetime, timezone
import redis  # Добавляем импорт redis для обработки ошибок

from app.config import settings
from app.database import redis_manager
from app.services.lcu_service import lcu_service
from app.services.discord_service import discord_service
from app.services.voice_service import voice_service
from app.endpoints import voice, auth, lcu, discord

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan with Windows optimizations."""
    logger.info("🚀 Starting LoL Voice Chat API on Windows...")
    await initialize_services()
    yield
    logger.info("🛑 Shutting down...")
    await cleanup_services()


async def initialize_services():
    """Initialize all services optimized for Windows."""
    logger.info("🚀 Initializing services for Windows...")
    
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
    
    # LCU service - Windows optimized
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

    logger.info("🎮 All services initialized for Windows!")
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


async def handle_champ_select(event_data: dict):
    """Handle champion selection phase - create voice rooms."""
    try:
        logger.info("🎯 Champion selection started - creating voice rooms")
        
        # Get detailed champ select data from event
        champ_select_data = event_data.get('champ_select_data')
        
        if not champ_select_data:
            # Fallback: try to get data directly
            champ_select_data = await lcu_service.get_champ_select_data()
        
        if champ_select_data:
            match_id = champ_select_data['match_id']
            players = champ_select_data['players']
            team_data = champ_select_data['teams']
            
            logger.info(f"🚀 Creating voice room for match {match_id}")
            logger.info(f"👥 Players: {len(players)}")
            logger.info(f"🔵 Blue team: {team_data.get('blue_team', [])}")
            logger.info(f"🔴 Red team: {team_data.get('red_team', [])}")
            
            # Create voice room
            result = await voice_service.create_voice_room(
                match_id,
                players,
                team_data
            )
            
            if 'error' in result:
                logger.error(f"❌ Failed to create voice room: {result['error']}")
            else:
                logger.info(f"✅ Successfully created voice room for match {match_id}")
                
                # Save match info for current user for auto-assignment
                current_summoner = await lcu_service.lcu_connector.get_current_summoner()
                if current_summoner:
                    summoner_id = str(current_summoner.get('summonerId'))
                    
                    # Use a dedicated key for match info to avoid Redis type conflicts
                    match_info_key = f"user_match:{summoner_id}"
                    
                    # Determine which team the current user is on
                    user_team = None
                    if summoner_id in team_data.get('blue_team', []):
                        user_team = "Blue Team"
                    elif summoner_id in team_data.get('red_team', []):
                        user_team = "Red Team"
                    
                    if user_team:
                        match_info = {
                            'match_id': match_id,
                            'team_name': user_team,
                            'assigned_at': datetime.now(timezone.utc).isoformat()
                        }
                        # Save to dedicated match info key
                        redis_manager.redis.setex(match_info_key, 3600, json.dumps(match_info))
                        logger.info(f"✅ Saved match info for user {summoner_id} in {user_team}")
                    else:
                        logger.warning(f"⚠️ Current user {summoner_id} not found in any team")
                else:
                    logger.warning("⚠️ Could not get current summoner data")
        else:
            logger.warning("⚠️ No champ select data available - cannot create voice room")
            
    except Exception as e:
        logger.error(f"❌ Error handling champ select: {e}")


async def handle_game_event(event_data: dict):
    """Handle game events from LCU."""
    try:
        event_type = event_data.get('phase')
        logger.info(f"🎮 Game event received: {event_type}")
        
        if event_type == "InProgress":
            await handle_match_start()
        elif event_type == "EndOfGame":
            await handle_match_end(event_data)
                        
    except Exception as e:
        logger.error(f"❌ Error handling game event: {e}")


async def handle_match_start():
    """Handle match start - perform auto-assignments."""
    try:
        logger.info("🎯 Match started - performing auto-assignments")
        
        # Get current summoner
        current_summoner = await lcu_service.lcu_connector.get_current_summoner()
        if not current_summoner:
            logger.warning("⚠️ No current summoner data available")
            return
            
        summoner_id = str(current_summoner.get('summonerId'))
        summoner_name = current_summoner.get('displayName', 'Unknown')
        logger.info(f"👤 Current summoner: {summoner_name} (ID: {summoner_id})")
        
        # Get saved match info from dedicated key
        match_info_key = f"user_match:{summoner_id}"
        match_info_data = redis_manager.redis.get(match_info_key)
        
        if match_info_data:
            match_info = json.loads(match_info_data)
            match_id = match_info.get('match_id')
            team_name = match_info.get('team_name')
            
            if match_id and team_name:
                logger.info(f"🎯 Auto-assigning user {summoner_name} to {team_name} in match {match_id}")
                
                # Get Discord user ID with proper error handling for Redis type issues
                user_key = f"user:{summoner_id}"
                discord_user_id = None
                
                try:
                    # Try to get as hash first (correct way)
                    discord_user_id = redis_manager.redis.hget(user_key, "discord_user_id")
                except redis.exceptions.ResponseError as e:
                    if "WRONGTYPE" in str(e):
                        logger.warning(f"⚠️ Redis key {user_key} has wrong type. Attempting to fix...")
                        try:
                            # If it's a string, try to parse it
                            user_data = redis_manager.redis.get(user_key)
                            if user_data:
                                try:
                                    user_info = json.loads(user_data)
                                    discord_user_id = user_info.get('discord_user_id')
                                    logger.info(f"✅ Recovered Discord ID from string key: {discord_user_id}")
                                except json.JSONDecodeError:
                                    logger.error(f"❌ Failed to parse user data as JSON: {user_data}")
                        except Exception as parse_error:
                            logger.error(f"❌ Failed to recover Discord ID: {parse_error}")
                    else:
                        raise e
                
                if discord_user_id:
                    success = await discord_service.assign_player_to_team(
                        int(discord_user_id),
                        match_id,
                        team_name
                    )
                    
                    if success:
                        logger.info(f"✅ Successfully auto-assigned {summoner_name} to {team_name}")
                        
                        # Get voice room to provide invite link
                        room_data = voice_service.redis.get_voice_room_by_match(match_id)
                        discord_channels = voice_service.get_voice_room_discord_channels(match_id)
                        
                        team_channel = None
                        if team_name == "Blue Team" and discord_channels.get('blue_team'):
                            team_channel = discord_channels['blue_team']
                        elif team_name == "Red Team" and discord_channels.get('red_team'):
                            team_channel = discord_channels['red_team']
                        
                        if team_channel and team_channel.get('invite_url'):
                            logger.info(f"🔗 Discord invite available: {team_channel['invite_url']}")
                            # Store invite URL for user access
                            invite_key = f"user_invite:{summoner_id}"
                            redis_manager.redis.setex(invite_key, 3600, team_channel['invite_url'])
                        else:
                            logger.warning("⚠️ No Discord channel invite URL available")
                    else:
                        logger.error("❌ Failed to assign user to team role in Discord")
                else:
                    logger.warning(f"⚠️ No Discord account linked for user {summoner_name}")
            else:
                logger.warning("⚠️ Incomplete match info saved")
        else:
            logger.warning("⚠️ No match info found for current user")
            
    except Exception as e:
        logger.error(f"❌ Error handling match start: {e}")


async def handle_match_end(event_data: dict):
    """Handle match end - cleanup voice rooms."""
    try:
        logger.info("🛑 Match ended - cleaning up voice rooms")
        
        # Get current summoner to find match info
        current_summoner = await lcu_service.lcu_connector.get_current_summoner()
        if current_summoner:
            summoner_id = str(current_summoner.get('summonerId'))
            
            # Get match info from dedicated key
            match_info_key = f"user_match:{summoner_id}"
            match_info_data = redis_manager.redis.get(match_info_key)
            
            if match_info_data:
                match_info = json.loads(match_info_data)
                match_id = match_info.get('match_id')
                
                if match_id:
                    logger.info(f"🧹 Cleaning up voice room for match {match_id}")
                    success = await voice_service.close_voice_room(match_id)
                    
                    if success:
                        logger.info(f"✅ Successfully cleaned up voice room for match {match_id}")
                    else:
                        logger.warning(f"⚠️ No active voice room found for match {match_id}")
                    
                    # Clean up user match info and invite
                    redis_manager.redis.delete(match_info_key)
                    invite_key = f"user_invite:{summoner_id}"
                    redis_manager.redis.delete(invite_key)
                    
    except Exception as e:
        logger.error(f"❌ Error handling match end: {e}")


async def handle_ready_check(event_data: dict):
    """Handle ready check phase."""
    try:
        logger.info("✅ Ready check detected")
        # Можно добавить логику для уведомлений о готовности
    except Exception as e:
        logger.error(f"❌ Error handling ready check: {e}")


# Create FastAPI app
app = FastAPI(
    title="LoL Voice Chat API - Windows",
    description="Discord voice chat integration for League of Legends - Windows Local Setup",
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
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    
    @app.get("/demo")
    async def demo_page():
        """Serve demo page for testing."""
        demo_file = os.path.join(static_dir, "demo.html")
        if os.path.exists(demo_file):
            return FileResponse(demo_file)
        raise HTTPException(status_code=404, detail="Demo file not found")

# Include routers
app.include_router(voice.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(lcu.router, prefix="/api")
app.include_router(discord.router, prefix="/api")


@app.get("/")
async def root():
    return {
        "message": "LoL Voice Chat API is running on Windows! 🎮",
        "status": "healthy",
        "platform": "windows",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.get("/health")
async def health_check():
    """Comprehensive health check for Windows."""
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
    
    # Сообщение для Windows
    if services["discord"] == "connected":
        message = "✅ Приложение работает на Windows! Discord подключен."
    elif services["discord"] == "mock_mode":
        message = "🔶 Приложение работает на Windows! Discord в режиме заглушки."
    else:
        message = "❌ Приложение работает на Windows! Discord не подключен."

    if services["lcu"] == "connected":
        message += " 🎮 LCU подключен к клиенту игры."
    elif services["lcu"] == "waiting_for_game":
        message += " 🔶 LCU ожидает запуск League of Legends."

    return JSONResponse(content={
        "status": "healthy",
        "services": services,
        "platform": "windows",
        "discord_details": discord_status,
        "lcu_details": await lcu_service.get_detailed_status(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "message": message
    })


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.SERVER_HOST,
        port=settings.SERVER_PORT,
        reload=settings.DEBUG
    )
