from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncio
from app.config import settings
from app.database import redis_manager
from app.services.lcu_service import lcu_service
from app.endpoints import voice, auth, lcu
from app.services.voice_service import voice_service
from app.utils.exceptions import exception_handlers
from app.websocket.voice_server import sio
from socketio import ASGIApp


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("Starting up...")
    # Initialize services
    try:
        await lcu_service.initialize()
        asyncio.create_task(lcu_service.start_monitoring(handle_game_event))
        print("LCU service initialized")
    except Exception as e:
        print(f"Failed to initialize LCU service: {e}")
    yield
    # Shutdown
    print("Shutting down...")
    await lcu_service.stop_monitoring()


async def handle_game_event(event_type: str, data: dict):
    """Handle game events from LCU"""
    if event_type == "match_start":
        print(f"Match started: {data['match_id']}")
        # Here you could automatically create voice rooms
    elif event_type == "match_end":
        print(f"Match ended: {data['match_id']}")
        # Automatically close voice rooms
        voice_service.close_voice_room(data['match_id'])
# Create FastAPI app
app = FastAPI(
    title="LoL Voice Chat API",
    lifespan=lifespan,
    exception_handlers=exception_handlers  # Добавляем обработчики исключений
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(voice.router)
app.include_router(auth.router)
app.include_router(lcu.router)

# Socket.IO app
sio_app = ASGIApp(sio, app)


@app.get("/")
async def root():
    return {"message": "LoL Voice Chat API"}


@app.get("/health")
async def health_check():
    return {"status": "healthy", "redis": redis_manager.redis.ping()}

# For running with uvicorn directly
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(sio_app, host=settings.SERVER_HOST, port=settings.SERVER_PORT)
