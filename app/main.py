from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
import asyncio
import logging
from app.config import settings
from app.database import redis_manager
from app.services.lcu_service import lcu_service
from app.endpoints import voice, auth, lcu
from app.services.voice_service import voice_service
from app.websocket.voice_server import sio
from socketio import ASGIApp
from fastapi.staticfiles import StaticFiles
import os  # Добавьте эту строку


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting up LoL Voice Chat API...")
    # Initialize LCU service (optional - only if League Client is running)
    lcu_initialized = False
    try:
        await lcu_service.initialize()
        asyncio.create_task(lcu_service.start_monitoring(handle_game_event))
        lcu_initialized = True
        logger.info("✅ LCU service initialized successfully")
    except Exception as e:
        logger.warning(f"⚠️ LCU service not available: {e}")
        logger.info("🔧 Application will run in standalone mode (without automatic game detection)")

    # Health check endpoint with LCU status
    @app.get("/health")
    async def health_check():
        redis_status = "unknown"
        try:
            redis_status = "healthy" if redis_manager.redis.ping() else "unhealthy"
        except:
            redis_status = "unhealthy"
        return {
            "status": "healthy",
            "redis": redis_status,
            "lcu_initialized": lcu_initialized,
            "mode": "standalone" if not lcu_initialized else "integrated"
        }
    yield
    # Shutdown
    logger.info("Shutting down...")
    try:
        if lcu_initialized:
            await lcu_service.stop_monitoring()
    except Exception as e:
        logger.error(f"Error during LCU shutdown: {e}")


async def handle_game_event(event_type: str, data: dict):
    """Handle game events from LCU"""
    try:
        if event_type == "match_start":
            logger.info(f"🎮 Match started: {data.get('match_id', 'unknown')}")
            # Here you could automatically create voice rooms
        elif event_type == "match_end":
            logger.info(f"🎮 Match ended: {data.get('match_id', 'unknown')}")
            # Automatically close voice rooms
            try:
                voice_service.close_voice_room(data['match_id'])
            except Exception as e:
                logger.error(f"Error closing voice room: {e}")
    except Exception as e:
        logger.error(f"Error handling game event: {e}")

# Create FastAPI app
app = FastAPI(
    title="LoL Voice Chat API",
    description="Voice chat overlay for League of Legends",
    version="1.0.0",
    lifespan=lifespan
)

# Serve static files if static directory exists
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

    @app.get("/demo")
    async def demo_page():
        """Serve demo page for testing"""
        return FileResponse("static/demo.html")
else:
    logger.warning("Static directory not found, skipping static file serving")

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

# Socket.IO app
sio_app = ASGIApp(sio, app)


@app.get("/")
async def root():
    return {
        "message": "LoL Voice Chat API is running!",
        "docs": "/docs",
        "health": "/health"
    }


@app.get("/api/info")
async def api_info():
    """Get API information"""
    return {
        "name": "LoL Voice Chat API",
        "version": "1.0.0",
        "status": "operational",
        "features": [
            "Voice room management",
            "WebRTC signaling",
            "LCU integration (optional)",
            "JWT authentication"
        ]
    }

# For running with uvicorn directly
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(sio_app, host=settings.SERVER_HOST, port=settings.SERVER_PORT)
