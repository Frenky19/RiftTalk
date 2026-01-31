import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import redis_manager
from app.endpoints import auth, discord, lcu, voice
from app.services.lcu_service import lcu_service
from app.services.remote_api import RemoteAPIError, remote_api
from app.services.shutdown_cleanup import notify_match_leave_on_shutdown
from app.utils.security import create_access_token

logger = logging.getLogger(__name__)


def _resolve_static_dir() -> str:
    """Resolve directory for static assets."""
    env_dir = os.environ.get('RIFT_STATIC_DIR')
    if env_dir and os.path.exists(env_dir):
        return env_dir

    # PyInstaller onefile extracts bundled data into sys._MEIPASS
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        mei_static = os.path.join(getattr(sys, '_MEIPASS'), 'static')
        if os.path.exists(mei_static):
            return mei_static
        # Fallback: if user ships a folder next to exe
        exe_static = os.path.join(os.path.dirname(sys.executable), 'static')
        return exe_static

    # Dev mode
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    base_static = os.path.join(project_root, 'static')
    nested_static = os.path.join(base_static, 'static')
    if os.path.exists(nested_static):
        return nested_static
    return base_static


static_dir = _resolve_static_dir()


async def validate_user_data_integrity():
    """Validate and fix user data integrity in storage."""
    try:
        logger.info('Validating user data integrity...')
        user_keys = []
        try:
            for key in await redis_manager.redis.scan_iter(match='user:*'):
                user_keys.append(key)
        except Exception as e:
            logger.error(f'Error scanning keys: {e}')
            return
        fixed_count = 0
        for key in user_keys:
            try:
                old_data = await redis_manager.redis.get(key)
                if old_data and isinstance(old_data, str):
                    try:
                        parsed_data = json.loads(old_data)
                        await redis_manager.redis.delete(key)
                        await redis_manager.redis.hset(key, mapping=parsed_data)
                        fixed_count += 1
                        logger.info(f'Fixed user key: {key}')
                    except json.JSONDecodeError:
                        await redis_manager.redis.delete(key)
                        await redis_manager.redis.hset(key, 'data', old_data)
                        fixed_count += 1
                        logger.info(f'Fixed string user key: {key}')
            except Exception as e:
                logger.error(f'Error fixing key {key}: {e}')
                continue
        if fixed_count > 0:
            logger.info(f'Fixed {fixed_count} user keys')
        else:
            logger.info('User data integrity check passed')
    except Exception as e:
        logger.error(f'User data integrity check failed: {e}')


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info('Starting RiftTalk client API...')
    await initialize_services()
    yield
    logger.info('Shutting down...')
    await cleanup_services()


async def auto_authenticate_via_lcu():
    """Automatically authenticate using LCU when available."""
    global auto_auth_token
    try:
        if await lcu_service.lcu_connector.connect():
            current_summoner = (
                await lcu_service.lcu_connector.get_current_summoner()
            )
            if current_summoner:
                summoner_id = str(current_summoner.get('summonerId'))
                summoner_name = current_summoner.get('displayName', 'Unknown')
                from datetime import timedelta
                access_token_expires = timedelta(
                    minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
                )
                access_token = create_access_token(
                    data={'sub': summoner_id, 'name': summoner_name},
                    expires_delta=access_token_expires
                )
                auto_auth_token = access_token
                logger.info(
                    f'Auto-authenticated as: {summoner_name} (ID: {summoner_id})'
                )
                return access_token
    except Exception as e:
        logger.warning(f'Auto-authentication failed: {e}')
    return None


async def initialize_services():
    """Initialize client services."""
    try:
        logger.info('Initializing LCU service...')
        await validate_user_data_integrity()
        await auto_authenticate_via_lcu()

        lcu_service.register_event_handler('match_start', handle_game_event)
        lcu_service.register_event_handler('match_end', handle_game_event)
        lcu_service.register_event_handler('phase_none', handle_game_event)
        lcu_service.register_event_handler('champ_select', handle_champ_select)
        lcu_service.register_event_handler('ready_check', handle_ready_check)
        await lcu_service.start_monitoring()
        logger.info('LCU service: MONITORING STARTED')
    except Exception as e:
        logger.error(f'LCU service failed to start: {e}')


async def cleanup_services():
    """Cleanup client services on shutdown."""
    try:
        try:
            await lcu_service.stop_monitoring()
        except Exception:
            pass
        try:
            if getattr(lcu_service, 'lcu_connector', None):
                await lcu_service.lcu_connector.disconnect()
        except Exception:
            pass
        try:
            await notify_match_leave_on_shutdown()
        except Exception:
            pass
    except Exception as e:
        logger.warning(f'Cleanup error: {e}')


async def handle_champ_select(event_data: dict):
    """Handle champion selection phase - DON'T create voice rooms yet."""
    try:
        logger.info('Champion selection started - WAITING for match start')
        champ_select_data = event_data.get('champ_select_data')
        if not champ_select_data:
            champ_select_data = await lcu_service.get_champ_select_data()
        if champ_select_data:
            match_id = champ_select_data['match_id']
            players = champ_select_data['players']
            team_data = champ_select_data['teams']
            current_summoner = (
                await lcu_service.lcu_connector.get_current_summoner()
            )
            if current_summoner:
                summoner_id = str(current_summoner.get('summonerId'))
                match_info_key = f'user_match:{summoner_id}'
                match_info = {
                    'pending_match_id': match_id,
                    'players': json.dumps(players),
                    'team_data': json.dumps(team_data),
                    'phase': 'ChampSelect',
                    'saved_at': datetime.now(timezone.utc).isoformat(),
                }
                await redis_manager.redis.hset(match_info_key, mapping=match_info)
                await redis_manager.redis.expire(match_info_key, 3600)
                logger.info(
                    f'Saved champ select info for match {match_id}, '
                    f'waiting for match start'
                )
        else:
            logger.warning('No champ select data available')
    except Exception as e:
        logger.error(f'Error handling champ select: {e}')


async def handle_game_event(event_data: dict):
    """Handle game events from LCU."""
    try:
        event_type = event_data.get('phase')
        prev_phase = event_data.get('previous_phase')
        logger.info(f'Game event received: {event_type}')

        if event_type == 'InProgress':
            await handle_match_start()
            return

        if event_type in ('EndOfGame',):
            await handle_match_end(event_data)
            return

        if event_type in ('None', 'Lobby'):
            if prev_phase in ('PreEndOfGame', 'EndOfGame'):
                await handle_match_end(event_data)
            else:
                await handle_match_leave(event_data)
            return

        if event_type == 'PreEndOfGame':
            logger.info('PreEndOfGame detected - waiting for match end')
            return
    except Exception as e:
        logger.error(f'Error handling game event: {e}')


async def handle_match_start():
    """Handle match start (client mode)."""
    try:
        logger.info('Match started - notifying remote server')
        try:
            current_phase = await lcu_service.lcu_connector.get_game_flow_phase()
            if current_phase != 'InProgress':
                return
        except Exception:
            return

        current_summoner = await lcu_service.lcu_connector.get_current_summoner()
        if not current_summoner:
            return
        summoner_id = str(current_summoner.get('summonerId'))
        summoner_name = current_summoner.get('displayName', 'Unknown')

        session = await lcu_service.lcu_connector.get_current_session()
        game_id = None
        if session:
            game_id = session.get('gameData', {}).get('gameId')
        if not game_id:
            return
        match_id = f'match_{game_id}'

        match_info_key = f'user_match:{summoner_id}'
        existing: dict[str, str] = {}
        try:
            raw = await redis_manager.redis.hgetall(match_info_key)
            existing = {
                (k.decode() if isinstance(k, (bytes, bytearray)) else str(k)):
                (v.decode() if isinstance(v, (bytes, bytearray)) else str(v))
                for k, v in (raw or {}).items()
            }
        except Exception:
            existing = {}

        now = datetime.now(timezone.utc)
        now_ts = now.timestamp()

        if existing.get('match_id') == match_id and existing.get('remote_notified') == '1':
            return

        if existing.get('match_id') == match_id:
            next_retry = existing.get('notify_next_retry_ts')
            if next_retry:
                try:
                    if now_ts < float(next_retry):
                        return
                except Exception:
                    pass

        try:
            await redis_manager.redis.hset(
                match_info_key,
                mapping={
                    'match_id': match_id,
                    'phase': 'InProgress',
                    'started_at': now.isoformat(),
                    'remote_notified': '0',
                    'notify_fail_count': existing.get('notify_fail_count', '0'),
                    'notify_next_retry_ts': existing.get('notify_next_retry_ts', '0'),
                },
            )
            await redis_manager.redis.expire(match_info_key, 3600)
        except Exception:
            pass
        try:
            user_key = f'user:{summoner_id}'
            await redis_manager.redis.hset(user_key, 'current_match', match_id)
        except Exception:
            pass

        teams_data = await lcu_service.lcu_connector.get_teams()
        blue_team_ids = [
            str(p.get('summonerId'))
            for p in (teams_data or {}).get('blue_team', [])
            if p.get('summonerId')
        ]
        red_team_ids = [
            str(p.get('summonerId'))
            for p in (teams_data or {}).get('red_team', [])
            if p.get('summonerId')
        ]

        payload = {
            'match_id': match_id,
            'summoner_id': summoner_id,
            'summoner_name': summoner_name,
            'blue_team': blue_team_ids,
            'red_team': red_team_ids,
        }
        try:
            await remote_api.match_start(payload)
            try:
                await redis_manager.redis.hset(
                    match_info_key,
                    mapping={
                        'remote_notified': '1',
                        'remote_notified_at': now.isoformat(),
                        'notify_fail_count': '0',
                        'notify_next_retry_ts': '0',
                    },
                )
            except Exception:
                pass
        except RemoteAPIError as e:
            logger.warning(f'Remote match-start failed: {e}')
            try:
                fail_count = (
                    int(existing.get('notify_fail_count', '0') or '0') + 1
                )
            except Exception:
                fail_count = 1
            delay = min(300, 5 * (2 ** max(0, fail_count - 1)))
            try:
                await redis_manager.redis.hset(
                    match_info_key,
                    mapping={
                        'remote_notified': '0',
                        'notify_fail_count': str(fail_count),
                        'notify_next_retry_ts': str(now_ts + delay),
                    },
                )
            except Exception:
                pass
    except Exception as e:
        logger.error(f'handle_match_start error: {e}')


async def handle_match_end(event_data: dict):
    """Handle match end (client mode)."""
    try:
        current_summoner = await lcu_service.lcu_connector.get_current_summoner()
        if not current_summoner:
            return
        summoner_id = str(current_summoner.get('summonerId'))

        match_id = None
        try:
            match_info_key = f'user_match:{summoner_id}'
            match_id = await redis_manager.redis.hget(match_info_key, 'match_id')
            if isinstance(match_id, (bytes, bytearray)):
                match_id = match_id.decode('utf-8', errors='ignore')
        except Exception:
            match_id = None

        if not match_id:
            session = await lcu_service.lcu_connector.get_current_session()
            if session and session.get('gameData', {}).get('gameId'):
                match_id = f"match_{session['gameData']['gameId']}"

        if not match_id:
            return

        try:
            await remote_api.match_end({'match_id': str(match_id)})
        except RemoteAPIError as e:
            logger.warning(f'Remote match-end failed: {e}')

        try:
            match_info_key = f'user_match:{summoner_id}'
            await redis_manager.redis.delete(match_info_key)
        except Exception:
            pass
        try:
            user_key = f'user:{summoner_id}'
            await redis_manager.redis.hdel(user_key, 'current_match')
        except Exception:
            pass
    except Exception as e:
        logger.error(f'handle_match_end error: {e}')


async def handle_match_leave(event_data: dict):
    """Handle early leave / crash (client mode)."""
    try:
        current_summoner = await lcu_service.lcu_connector.get_current_summoner()
        if not current_summoner:
            return
        summoner_id = str(current_summoner.get('summonerId'))

        match_id = None
        try:
            user_key = f'user:{summoner_id}'
            match_id = await redis_manager.redis.hget(user_key, 'current_match')
        except Exception:
            match_id = None

        if not match_id:
            return

        try:
            await remote_api.match_leave(
                {
                    'match_id': str(match_id),
                    'summoner_id': str(summoner_id),
                }
            )
        except RemoteAPIError as e:
            logger.warning(f'Remote match-leave failed: {e}')

        try:
            user_key = f'user:{summoner_id}'
            await redis_manager.redis.hdel(user_key, 'current_match')
        except Exception:
            pass
    except Exception as e:
        logger.error(f'handle_match_leave error: {e}')


async def handle_ready_check(event_data: dict):
    """Handle ready check phase."""
    try:
        logger.info('Ready check detected')
    except Exception as e:
        logger.error(f'Error handling ready check: {e}')


app = FastAPI(
    title='RiftTalk Client API',
    description='Client-side LCU integration and UI',
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
else:
    base_dir_fallback = os.path.dirname(os.path.abspath(__file__))
    static_dir_fallback = os.path.join(base_dir_fallback, 'static')
    if os.path.exists(static_dir_fallback):
        app.mount('/static', StaticFiles(directory=static_dir_fallback), name='static')
        static_dir = static_dir_fallback
        logger.info(f'Static files served from fallback: {static_dir}')
    else:
        logger.error('Static directory not found!')


@app.get('/link-discord')
async def link_discord_page():
    link_discord_file = os.path.join(static_dir, 'link-discord.html')
    if os.path.exists(link_discord_file):
        return FileResponse(link_discord_file)
    raise HTTPException(status_code=404, detail='Link Discord page not found')


app.include_router(auth.router, prefix='/api')
app.include_router(lcu.router, prefix='/api')
app.include_router(discord.router, prefix='/api')
app.include_router(voice.router, prefix='/api')


@app.get('/api/health')
async def health():
    return {'ok': True, 'mode': 'client'}


@app.get('/')
async def root():
    return {
        'message': 'RiftTalk Client API is running',
        'status': 'healthy',
        'platform': 'windows',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'auto_auth_available': 'auto_auth_token' in globals()
    }


@app.get('/health')
async def health_check():
    services = {
        'api': 'healthy',
        'redis': 'checking...',
        'lcu': 'checking...'
    }
    try:
        services['redis'] = 'healthy' if await redis_manager.redis.ping() else 'unhealthy'
    except Exception as e:
        services['redis'] = f'error: {str(e)}'

    try:
        lcu_details = await lcu_service.get_detailed_status()
        if lcu_details.get('connected'):
            services['lcu'] = 'connected'
        elif lcu_details.get('initialized'):
            services['lcu'] = 'waiting_for_game'
        else:
            services['lcu'] = 'disconnected'
    except Exception:
        services['lcu'] = 'unavailable'

    message = 'Client running on Windows.'
    if services['lcu'] == 'connected':
        message += ' LCU connected to game client.'
    elif services['lcu'] == 'waiting_for_game':
        message += ' LCU waiting for League of Legends launch.'

    return JSONResponse(content={
        'status': 'healthy',
        'services': services,
        'platform': 'windows',
        'lcu_details': await lcu_service.get_detailed_status(),
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'message': message,
        'auto_auth_available': 'auto_auth_token' in globals()
    })
