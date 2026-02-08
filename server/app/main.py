import asyncio
import logging
import os
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.constants import RATE_LIMIT_KEY_TTL_SECONDS, RATE_LIMIT_WINDOW_SECONDS
from app.database import redis_manager
from app.endpoints import client_remote, public_discord
from app.services.cleanup_service import cleanup_service
from app.services.discord_service import discord_service

logger = logging.getLogger(__name__)


def _resolve_repo_root() -> str:
    return os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )


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


def _resolve_marketing_dir() -> str:
    env_dir = os.environ.get('RIFT_MARKETING_DIR') or os.environ.get(
        'RIFT_SITE_DIR'
    )
    if env_dir:
        candidate = env_dir
        if not os.path.isabs(candidate):
            candidate = os.path.join(_resolve_repo_root(), candidate)
        index_path = os.path.join(candidate, 'index.html')
        if os.path.exists(index_path):
            return candidate

    default_dir = os.path.join(_resolve_repo_root(), 'rifttalk-site')
    index_path = os.path.join(default_dir, 'index.html')
    if os.path.exists(index_path):
        return default_dir

    return ''


static_dir = _resolve_static_dir()
marketing_dir = _resolve_marketing_dir()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info('Starting RiftTalk server API...')
    await initialize_services()
    yield
    logger.info('Shutting down...')
    await cleanup_services()


async def initialize_services():
    if not settings.discord_enabled:
        raise RuntimeError(
            'Server mode requires Discord config. '
            'Set DISCORD_BOT_TOKEN and DISCORD_GUILD_ID in .env'
        )

    try:
        await discord_service.connect()
        if discord_service.connected:
            logger.info('Discord service: CONNECTED')
        else:
            logger.warning('Discord service: NOT CONNECTED (will retry)')
            discord_service.schedule_reconnect('startup_not_connected')
    except Exception as e:
        logger.error(f'Discord service failed to start: {e}')
        discord_service.schedule_reconnect('startup_exception')

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
            await discord_service.disconnect(intentional=True)
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


@app.middleware('http')
async def rate_limit_middleware(request: Request, call_next):
    if not getattr(settings, 'RIFT_RATE_LIMIT_ENABLED', True):
        return await call_next(request)

    path = request.url.path
    if path.startswith('/api/client/') or path.startswith('/api/public/discord/'):
        if path.endswith('/callback'):
            return await call_next(request)
        client_ip = request.headers.get('x-forwarded-for', '').split(',')[0].strip()
        if not client_ip:
            client_ip = request.client.host if request.client else 'unknown'

        window = int(time.time() // RATE_LIMIT_WINDOW_SECONDS)
        key = f'rl:{client_ip}:{window}'
        try:
            count = await redis_manager.redis.incr(key, 1)
            if int(count) == 1:
                await redis_manager.redis.expire(
                    key,
                    RATE_LIMIT_KEY_TTL_SECONDS,
                )
            limit = int(getattr(settings, 'RIFT_RATE_LIMIT_PER_MINUTE', 60) or 60)
            if int(count) > limit:
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={'detail': 'Rate limit exceeded'},
                )
        except Exception:
            pass

    return await call_next(request)


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


if os.path.exists(static_dir):
    app.mount('/static', StaticFiles(directory=static_dir), name='static')
    logger.info(f'Static files served from: {static_dir}')


app.include_router(public_discord.router, prefix='/api')
app.include_router(client_remote.router, prefix='/api')


@app.get('/api/health')
async def health():
    return {
        'ok': True,
        'mode': 'server',
    }


@app.get('/health')
async def health_check():
    services = {
        'api': 'healthy',
        'redis': 'checking...',
        'discord': 'checking...'
    }
    try:
        services['redis'] = (
            'healthy' if await redis_manager.redis.ping() else 'unhealthy'
        )
    except Exception as e:
        services['redis'] = f'error: {str(e)}'

    discord_status = discord_service.get_status()
    services['discord'] = (
        'connected' if discord_status.get('connected') else 'disconnected'
    )
    redis_details = {}
    try:
        redis_details = redis_manager.redis_health()
    except Exception:
        redis_details = {}

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
        'redis_details': redis_details,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'message': message,
    })


@app.get('/.git/{path:path}', include_in_schema=False)
async def block_git_access(path: str):
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={'detail': 'Not found'},
    )


if marketing_dir:
    app.mount(
        '/',
        StaticFiles(directory=marketing_dir, html=True),
        name='marketing',
    )
    logger.info(f'Marketing site served from: {marketing_dir}')
else:

    @app.get('/')
    async def root():
        return {
            'message': 'RiftTalk Server API is running',
            'status': 'healthy',
            'platform': 'windows',
            'timestamp': datetime.now(timezone.utc).isoformat(),
        }
