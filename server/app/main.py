import logging
import os
import sys
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import redis_manager
from app.endpoints import client_remote, public_discord
from app.services.cleanup_service import cleanup_service
from app.services import persistent_store
from app.services.discord_service import discord_service


logger = logging.getLogger(__name__)


def _resolve_static_dir() -> str:
    env_dir = os.environ.get('RIFT_STATIC_DIR')
    if env_dir and os.path.exists(env_dir):
        return env_dir

    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        mei_static = os.path.join(getattr(sys, '_MEIPASS'), 'static')
        if os.path.exists(mei_static):
            return mei_static
        exe_static = os.path.join(os.path.dirname(sys.executable), 'static')
        return exe_static

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(project_root, 'static')


static_dir = _resolve_static_dir()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info('Starting RiftTalk server API...')
    await initialize_services()
    yield
    logger.info('Shutting down...')
    await cleanup_services()


async def initialize_services():
    try:
        db_path = persistent_store.init_db()
        logger.info(f'Persistent DB ready: {db_path}')
    except Exception as e:
        logger.warning(f'Persistent DB init failed: {e}')

    if not settings.discord_enabled:
        raise RuntimeError(
            'Server mode requires Discord config. '
            'Set DISCORD_BOT_TOKEN and DISCORD_GUILD_ID in .env'
        )

    async def _discord_reconnect_loop():
        backoff = 5
        while True:
            try:
                if not discord_service.connected:
                    await discord_service.connect()
                backoff = 5
            except Exception as e:
                logger.warning(f'Discord reconnect attempt failed: {e}')
                backoff = min(60, backoff * 2)
            await asyncio.sleep(backoff)

    try:
        await discord_service.connect()
        if discord_service.connected:
            logger.info('Discord service: CONNECTED')
        else:
            logger.warning('Discord service: NOT CONNECTED (will retry)')
            asyncio.create_task(_discord_reconnect_loop())
    except Exception as e:
        logger.error(f'Discord service failed to start: {e}')
        asyncio.create_task(_discord_reconnect_loop())

    try:
        await cleanup_service.start_cleanup_service()
        logger.info('Cleanup service: STARTED')
    except Exception as e:
        logger.warning(f'Cleanup service failed to start: {e}')


async def cleanup_services():
    try:
        try:
            await cleanup_service.stop_cleanup_service()
        except Exception:
            pass
        try:
            await discord_service.disconnect()
        except Exception:
            pass
    except Exception as e:
        logger.warning(f'Cleanup error: {e}')


app = FastAPI(
    title='RiftTalk Server API',
    description='Discord bot + public endpoints',
    version='1.0.1',
    lifespan=lifespan,
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError
):
    logger.error(f'Validation error for {request.url}:')
    logger.error(f'Request body: {await request.body()}')
    logger.error(f'Errors: {exc.errors()}')
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            'detail': 'Validation error',
            'errors': exc.errors(),
            'body_received': str(await request.body())
        },
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

if os.path.exists(static_dir):
    app.mount('/static', StaticFiles(directory=static_dir), name='static')
    logger.info(f'Static files served from: {static_dir}')


app.include_router(public_discord.router, prefix='/api')
app.include_router(client_remote.router, prefix='/api')


@app.get('/api/health')
async def health():
    return {'ok': True, 'mode': 'server'}


@app.get('/')
async def root():
    return {
        'message': 'RiftTalk Server API is running',
        'status': 'healthy',
        'platform': 'windows',
        'timestamp': datetime.now(timezone.utc).isoformat(),
    }


@app.get('/health')
async def health_check():
    services = {
        'api': 'healthy',
        'redis': 'checking...',
        'discord': 'checking...'
    }
    try:
        services['redis'] = 'healthy' if redis_manager.redis.ping() else 'unhealthy'
    except Exception as e:
        services['redis'] = f'error: {str(e)}'

    discord_status = discord_service.get_status()
    services['discord'] = 'connected' if discord_status.get('connected') else 'disconnected'

    message = 'Server running on Windows.'
    if services['discord'] == 'connected':
        message += ' Discord connected.'
    else:
        message += ' Discord not connected.'

    return JSONResponse(content={
        'status': 'healthy',
        'services': services,
        'platform': 'windows',
        'discord_details': discord_status,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'message': message,
    })
