import json
import logging
import os
import sys
import asyncio
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
from app.endpoints import public_discord, client_remote
from app.services.cleanup_service import cleanup_service
from app.services.discord_service import discord_service
from app.services.lcu_service import lcu_service
from app.services.voice_service import voice_service
from app.services.remote_api import remote_api, RemoteAPIError
from app.services.shutdown_cleanup import notify_match_leave_on_shutdown
from app.utils.security import create_access_token


logger = logging.getLogger(__name__)

def _resolve_static_dir() -> str:
    """Resolve directory for static assets.

    Goals:
      - In PyInstaller onefile mode, use the embedded extraction dir
        (sys._MEIPASS/static) and do NOT create/copy a ./static folder next
        to the executable.
      - In dev mode, use project_root/static.
      - Allow override via env var RIFT_STATIC_DIR.
    """
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
    return os.path.join(project_root, 'static')


static_dir = _resolve_static_dir()


async def validate_user_data_integrity():
    """Validate and fix user data integrity in storage."""
    try:
        logger.info('Validating user data integrity...')
        # Use scan_iter to find user keys
        user_keys = []
        try:
            for key in redis_manager.redis.scan_iter(match='user:*'):
                user_keys.append(key)
        except Exception as e:
            logger.error(f'Error scanning keys: {e}')
            return
        fixed_count = 0
        for key in user_keys:
            try:
                # For MemoryStorage we can't check type, so just try to get data
                old_data = redis_manager.redis.get(key)
                if old_data and isinstance(old_data, str):
                    try:
                        parsed_data = json.loads(old_data)
                        # If it's a string that parses as JSON, convert to hash
                        redis_manager.redis.delete(key)
                        redis_manager.redis.hset(key, mapping=parsed_data)
                        fixed_count += 1
                        logger.info(f'Fixed user key: {key}')
                    except json.JSONDecodeError:
                        # If it's not JSON, create simple hash
                        redis_manager.redis.delete(key)
                        redis_manager.redis.hset(key, 'data', old_data)
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
    """Application lifespan with Windows optimizations."""
    logger.info('Starting LoL Voice Chat API on Windows...')
    await initialize_services()
    yield
    logger.info('Shutting down...')
    await cleanup_services()


async def auto_authenticate_via_lcu():
    """Automatically authenticate using LCU when available."""
    global auto_auth_token
    if not settings.is_client:
        return
    try:
        if await lcu_service.lcu_connector.connect():
            current_summoner = (
                await lcu_service.lcu_connector.get_current_summoner()
            )
            if current_summoner:
                summoner_id = str(current_summoner.get('summonerId'))
                summoner_name = current_summoner.get('displayName', 'Unknown')
                # Create token automatically
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
    """Initialize services based on APP_MODE."""
    global lcu_status, discord_status

    if settings.is_client:
        # LCU
        try:
            lcu_status = 'initializing'
            logger.info('Initializing LCU service...')
            await validate_user_data_integrity()
            # Auto-auth (best-effort)
            await auto_authenticate_via_lcu()

            # Initialize LCU monitoring
            lcu_service.register_event_handler('match_start', handle_game_event)
            lcu_service.register_event_handler('match_end', handle_game_event)
            lcu_service.register_event_handler('phase_none', handle_game_event)
            lcu_service.register_event_handler('champ_select', handle_champ_select)
            lcu_service.register_event_handler('ready_check', handle_ready_check)
            await lcu_service.start_monitoring()
            lcu_status = 'monitoring'
            logger.info('LCU service: MONITORING STARTED')
        except Exception as e:
            lcu_status = f'error: {e}'
            logger.error(f'LCU service failed to start: {e}')

        # Discord bot is remote in client mode
        discord_status = 'remote'
        logger.info('Discord service: REMOTE (client mode)')
        return

    # --- server mode ---
    lcu_status = 'disabled'
    logger.info('LCU service: DISABLED (server mode)')

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

    discord_status = 'disconnected'
    try:
        await discord_service.connect()
        if discord_service.connected:
            discord_status = 'connected'
            logger.info('Discord service: CONNECTED')
        else:
            discord_status = 'retrying'
            logger.warning('Discord service: NOT CONNECTED (will retry)')
            asyncio.create_task(_discord_reconnect_loop())
    except Exception as e:
        discord_status = f'error: {e}'
        logger.error(f'Discord service failed to start: {e}')
        asyncio.create_task(_discord_reconnect_loop())

    # Cleanup service should run only on server
    try:
        await cleanup_service.start_cleanup_service()
        logger.info('Cleanup service: STARTED')
    except Exception as e:
        logger.warning(f'Cleanup service failed to start: {e}')


async def cleanup_services():
    """Cleanup services on shutdown."""
    try:
        # Always close LCU resources if they were created.
        # Even in server mode we may have instantiated the connector, which owns
        # an aiohttp ClientSession and will emit "Unclosed client session" on shutdown
        # if we don't close it.
        try:
            await lcu_service.stop_monitoring()
        except Exception:
            pass

        # stop_monitoring() cancels polling but doesn't close aiohttp session.
        try:
            if getattr(lcu_service, "lcu_connector", None):
                await lcu_service.lcu_connector.disconnect()
        except Exception:
            pass

        if settings.is_client:
            try:
                await notify_match_leave_on_shutdown()
            except Exception:
                pass
            return

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


async def handle_champ_select(event_data: dict):
    """Handle champion selection phase - DON'T create voice rooms yet."""
    try:
        logger.info('Champion selection started - WAITING for match start')
        # Get detailed champ select data from event
        champ_select_data = event_data.get('champ_select_data')
        if not champ_select_data:
            champ_select_data = await lcu_service.get_champ_select_data()
        if champ_select_data:
            match_id = champ_select_data['match_id']
            players = champ_select_data['players']
            team_data = champ_select_data['teams']
            # Save match info for future use
            current_summoner = (
                await lcu_service.lcu_connector.get_current_summoner()
            )
            if current_summoner:
                summoner_id = str(current_summoner.get('summonerId'))
                match_info_key = f'user_match:{summoner_id}'
                # IMPORTANT:
                # ChampSelect produces a synthetic match id like "champ_select_<ts>".
                # We must NOT store it as the active "match_id" because:
                # - /discord/match-status could create channels for that id
                # - EndOfGame cleanup would delete the wrong room
                # Instead, we keep it as *pending* metadata only.
                match_info = {
                    'pending_match_id': match_id,
                    'players': json.dumps(players),
                    'team_data': json.dumps(team_data),
                    'phase': 'ChampSelect',
                    'saved_at': datetime.now(timezone.utc).isoformat(),
                }
                redis_manager.redis.hset(match_info_key, mapping=match_info)
                redis_manager.redis.expire(match_info_key, 3600)
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

        # Match start
        if event_type == 'InProgress':
            await handle_match_start()
            return

        # LCU may or may not emit EndOfGame. Many clients go:
        # InProgress -> PreEndOfGame -> None.
        if event_type in ('EndOfGame',):
            await handle_match_end(event_data)
            return

        # We treat a transition to None/Lobby differently depending on
        # the previous phase.
        if event_type in ('None', 'Lobby'):
            # If we were in an end-of-game phase, this is a full match end.
            if prev_phase in ('PreEndOfGame', 'EndOfGame'):
                await handle_match_end(event_data)
            else:
                # Otherwise it is most likely an early leave/crash of this player.
                await handle_match_leave(event_data)
            return

        # PreEndOfGame doesn't require action on its own.
        if event_type == 'PreEndOfGame':
            logger.info('PreEndOfGame detected - waiting for match end')
            return
    except Exception as e:
        logger.error(f'Error handling game event: {e}')


def safe_json_parse(data, default=None):
    """Safely parse JSON data with error handling."""
    if data is None:
        return default
    if isinstance(data, (list, dict)):
        return data
    if isinstance(data, str):
        try:
            return json.loads(data)
        except json.JSONDecodeError:
            if ',' in data:
                return [
                    item.strip()
                    for item in data.split(',')
                    if item.strip()
                ]
            return default
    return default


async def auto_assign_player_to_existing_room(
    summoner_id: str,
    match_id: str,
    room_data: dict
):
    """Auto-assign player to existing room."""
    try:
        logger.info(
            f'Assigning player {summoner_id} to existing room for match {match_id}'
        )
        # Determine player team
        blue_team = safe_json_parse(room_data.get('blue_team'), [])
        red_team = safe_json_parse(room_data.get('red_team'), [])
        team_name = None
        if summoner_id in blue_team:
            team_name = 'Blue Team'
        elif summoner_id in red_team:
            team_name = 'Red Team'
        if team_name:
            # Get Discord user ID
            user_key = f'user:{summoner_id}'
            discord_user_id = None
            try:
                discord_user_id = redis_manager.redis.hget(
                    user_key,
                    'discord_user_id'
                )
            except Exception as e:
                logger.error(f'Error getting Discord ID: {e}')
            if discord_user_id:
                success = await discord_service.assign_player_to_team(
                    int(discord_user_id),
                    match_id,
                    team_name
                )
                if success:
                    logger.info(
                        f'Successfully assigned {summoner_id} to {team_name} '
                        f'in existing room'
                    )
                    await voice_service.add_player_to_existing_room(
                        summoner_id,
                        match_id,
                        team_name
                    )
                    discord_channels = (
                        voice_service.get_voice_room_discord_channels(match_id)
                    )
                    team_channel = None
                    if (
                        team_name == 'Blue Team' and discord_channels.get('blue_team')
                    ):
                        team_channel = discord_channels['blue_team']
                    elif (
                        team_name == 'Red Team' and discord_channels.get('red_team')
                    ):
                        team_channel = discord_channels['red_team']
                    if team_channel and team_channel.get('invite_url'):
                        logger.info(
                            f'Discord invite available: '
                            f'{team_channel["invite_url"]}'
                        )
                        # Store invite URL for user access
                        invite_key = f'user_invite:{summoner_id}'
                        redis_manager.redis.setex(
                            invite_key,
                            3600,
                            team_channel['invite_url']
                        )
                        # If the user is already in a voice channel (e.g. Waiting Room),
                        # move them to their team channel immediately (no need to re-join).
                        try:
                            await discord_service.move_member_to_team_channel_if_in_voice(
                                int(discord_user_id),
                                match_id,
                                team_name
                            )
                        except Exception as e:
                            logger.warning(f'Auto-move to team channel failed: {e}')
                    else:
                        logger.warning('No Discord channel invite URL available')
                else:
                    logger.error('Failed to assign user to team role in Discord')
            else:
                logger.warning(
                    f'No Discord account linked for user {summoner_id}'
                )
        else:
            logger.warning(
                f'Could not determine team for user {summoner_id} '
                f'in existing room'
            )
    except Exception as e:
        logger.error(f'Error auto-assigning to existing room: {e}')


async def handle_match_start():
    """Handle match start.

    Client mode: notify remote server (single bot) with match/team payload.
    """
    try:
        if not settings.is_client:
            return

        logger.info('Match started - notifying remote server')
        # Confirm phase
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

        # Deduplicate: LCU can briefly reconnect and emit InProgress multiple times.
        # Also protect the remote VPS from spam if the monitor loop fires too often.
        match_info_key = f'user_match:{summoner_id}'
        existing: dict[str, str] = {}
        try:
            raw = redis_manager.redis.hgetall(match_info_key)
            existing = {
                (k.decode() if isinstance(k, (bytes, bytearray)) else str(k)):
                (v.decode() if isinstance(v, (bytes, bytearray)) else str(v))
                for k, v in (raw or {}).items()
            }
        except Exception:
            existing = {}

        now = datetime.now(timezone.utc)
        now_ts = now.timestamp()

        # If we already notified remote server for this exact match, do nothing.
        if existing.get('match_id') == match_id and existing.get('remote_notified') == '1':
            return

        # If previous notify attempt failed, respect backoff.
        if existing.get('match_id') == match_id:
            next_retry = existing.get('notify_next_retry_ts')
            if next_retry:
                try:
                    if now_ts < float(next_retry):
                        return
                except Exception:
                    pass

        # Persist active match_id locally (helps UI + early leave cleanup)
        try:
            redis_manager.redis.hset(
                match_info_key,
                mapping={
                    'match_id': match_id,
                    'phase': 'InProgress',
                    'started_at': now.isoformat(),
                    # Notification state for remote VPS
                    'remote_notified': '0',
                    'notify_fail_count': existing.get('notify_fail_count', '0'),
                    'notify_next_retry_ts': existing.get('notify_next_retry_ts', '0'),
                },
            )
            redis_manager.redis.expire(match_info_key, 3600)
        except Exception:
            pass
        try:
            user_key = f'user:{summoner_id}'
            redis_manager.redis.hset(user_key, 'current_match', match_id)
        except Exception:
            pass

        teams_data = await lcu_service.lcu_connector.get_teams()
        blue_team_ids = [str(p.get('summonerId')) for p in (teams_data or {}).get('blue_team', []) if p.get('summonerId')]
        red_team_ids = [str(p.get('summonerId')) for p in (teams_data or {}).get('red_team', []) if p.get('summonerId')]

        payload = {
            'match_id': match_id,
            'summoner_id': summoner_id,
            'summoner_name': summoner_name,
            'blue_team': blue_team_ids,
            'red_team': red_team_ids,
        }
        try:
            await remote_api.match_start(payload)

            # Mark as successfully notified, so we don't spam the VPS.
            try:
                redis_manager.redis.hset(
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

            # Backoff retries to avoid hammering the remote server if the network is down.
            try:
                fail_count = int(existing.get('notify_fail_count', '0') or '0') + 1
            except Exception:
                fail_count = 1
            delay = min(300, 5 * (2 ** max(0, fail_count - 1)))  # 5,10,20,40,80,160,300...
            try:
                redis_manager.redis.hset(
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
        if not settings.is_client:
            return

        # Get current summoner and active match_id
        current_summoner = await lcu_service.lcu_connector.get_current_summoner()
        if not current_summoner:
            return
        summoner_id = str(current_summoner.get('summonerId'))

        match_id = None
        try:
            match_info_key = f'user_match:{summoner_id}'
            match_id = redis_manager.redis.hget(match_info_key, 'match_id')
            if isinstance(match_id, (bytes, bytearray)):
                match_id = match_id.decode('utf-8', errors='ignore')
        except Exception:
            match_id = None

        if not match_id:
            # best effort from session cache
            session = await lcu_service.lcu_connector.get_current_session()
            if session and session.get('gameData', {}).get('gameId'):
                match_id = f"match_{session['gameData']['gameId']}"

        if not match_id:
            return

        try:
            await remote_api.match_end({'match_id': str(match_id)})
        except RemoteAPIError as e:
            logger.warning(f'Remote match-end failed: {e}')

        # Local cleanup of pointers
        try:
            match_info_key = f'user_match:{summoner_id}'
            redis_manager.redis.delete(match_info_key)
        except Exception:
            pass
        try:
            user_key = f'user:{summoner_id}'
            redis_manager.redis.hdel(user_key, 'current_match')
        except Exception:
            pass
    except Exception as e:
        logger.error(f'handle_match_end error: {e}')


async def handle_match_leave(event_data: dict):
    """Handle early leave / crash (client mode)."""
    try:
        if not settings.is_client:
            return

        current_summoner = await lcu_service.lcu_connector.get_current_summoner()
        if not current_summoner:
            return
        summoner_id = str(current_summoner.get('summonerId'))

        match_id = None
        try:
            user_key = f'user:{summoner_id}'
            match_id = redis_manager.redis.hget(user_key, 'current_match')
        except Exception:
            match_id = None

        if not match_id:
            return

        try:
            await remote_api.match_leave({'match_id': str(match_id), 'summoner_id': str(summoner_id)})
        except RemoteAPIError as e:
            logger.warning(f'Remote match-leave failed: {e}')

        try:
            user_key = f'user:{summoner_id}'
            redis_manager.redis.hdel(user_key, 'current_match')
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


# Create FastAPI app
app = FastAPI(
    title='LoL Voice Chat API - Windows',
    description='Discord voice chat integration for League of Legends',
    version='1.0.1',
    lifespan=lifespan,
)


# Add handler for logging validation errors
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError
):
    """Log validation errors for debugging."""
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

# CORS middleware
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
    # If in built app static is not next to exe, try to find relative to current file
    base_dir_fallback = os.path.dirname(os.path.abspath(__file__))
    static_dir_fallback = os.path.join(base_dir_fallback, 'static')
    if os.path.exists(static_dir_fallback):
        app.mount(
            '/static',
            StaticFiles(directory=static_dir_fallback),
            name='static'
        )
        static_dir = static_dir_fallback
        logger.info(f'Static files served from fallback: {static_dir}')
    else:
        logger.error('Static directory not found!')


@app.get('/link-discord')
async def link_discord_page():
    """Serve Discord linking page (public access)."""
    link_discord_file = os.path.join(static_dir, 'link-discord.html')
    if os.path.exists(link_discord_file):
        return FileResponse(link_discord_file)
    raise HTTPException(status_code=404, detail='Link Discord page not found')


# Include routers
if settings.is_client:
    app.include_router(voice.router, prefix='/api')
    app.include_router(auth.router, prefix='/api')
    app.include_router(lcu.router, prefix='/api')
    app.include_router(discord.router, prefix='/api')
else:
    app.include_router(public_discord.router, prefix='/api')
    app.include_router(client_remote.router, prefix='/api')


@app.get('/api/health')
async def health():
    return {'ok': True, 'mode': settings.APP_MODE}


@app.get('/')
async def root():
    """Root endpoint."""
    return {
        'message': 'LoL Voice Chat API is running on Windows!',
        'status': 'healthy',
        'platform': 'windows',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'auto_auth_available': 'auto_auth_token' in globals()
    }


@app.get('/health')
async def health_check():
    """Comprehensive health check for Windows."""
    services = {
        'api': 'healthy',
        'redis': 'checking...',
        'discord': 'checking...',
        'lcu': 'checking...'
    }
    # Redis health
    try:
        services['redis'] = 'healthy' if redis_manager.redis.ping() else 'unhealthy'
    except Exception as e:
        services['redis'] = f'error: {str(e)}'
    # Discord health
    discord_status = discord_service.get_status()
    services['discord'] = 'connected' if discord_status.get('connected') else 'disconnected'
    # LCU health
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
    # Message for Windows
    if services['discord'] == 'connected':
        message = 'Application running on Windows! Discord connected.'
    else:
        message = 'Application running on Windows! Discord not connected.'

    if services['lcu'] == 'connected':
        message += ' LCU connected to game client.'
    elif services['lcu'] == 'waiting_for_game':
        message += ' LCU waiting for League of Legends launch.'
    return JSONResponse(content={
        'status': 'healthy',
        'services': services,
        'platform': 'windows',
        'discord_details': discord_status,
        'lcu_details': await lcu_service.get_detailed_status(),
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'message': message,
        'auto_auth_available': 'auto_auth_token' in globals()
    })


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(
        'app.main:app',
        host=settings.SERVER_HOST,
        port=settings.SERVER_PORT,
        reload=settings.DEBUG
    )
