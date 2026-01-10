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
from app.endpoints import auth, demo, discord, lcu, voice
from app.middleware.demo_auth import DemoAuthMiddleware
from app.services.cleanup_service import cleanup_service
from app.services.discord_service import discord_service
from app.services.lcu_service import lcu_service
from app.services.voice_service import voice_service
from app.utils.security import create_access_token


logger = logging.getLogger(__name__)

# Determine base directory for static files
if getattr(sys, 'frozen', False):
    # If running as exe
    base_dir = os.path.dirname(sys.executable)
else:
    # In development mode
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


static_dir = os.path.join(base_dir, 'static')


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
    """Initialize all services optimized for Windows."""
    logger.info('Initializing services for Windows...')
    # Check user data integrity
    await validate_user_data_integrity()
    # Automatic authentication via LCU
    await auto_authenticate_via_lcu()
    # Discord service
    discord_status = 'disabled'
    if settings.DISCORD_BOT_TOKEN:
        try:
            discord_initialized = await discord_service.connect()
            if discord_initialized:
                if discord_service.connected:
                    discord_status = 'connected'
                    logger.info('Discord service: CONNECTED')
                else:
                    discord_status = 'mock_mode'
                    logger.info('Discord service: MOCK MODE')
            else:
                discord_status = 'failed'
                logger.warning('Discord service: FAILED')
        except Exception as e:
            discord_status = f'error: {e}'
            logger.error(f'Discord service: ERROR - {e}')
    else:
        logger.info('Discord service: DISABLED (no token)')
    # LCU service - Windows optimized
    lcu_status = 'disconnected'
    try:
        lcu_initialized = await lcu_service.initialize()
        if lcu_initialized:
            lcu_status = 'initialized'
            logger.info('LCU service: INITIALIZED')
            # Register event handlers
            lcu_service.register_event_handler(
                'match_start',
                handle_game_event
            )
            lcu_service.register_event_handler(
                'match_end',
                handle_game_event
            )
            lcu_service.register_event_handler(
                'phase_none',
                handle_game_event
            )
            lcu_service.register_event_handler(
                'champ_select',
                handle_champ_select
            )
            lcu_service.register_event_handler(
                'ready_check',
                handle_ready_check
            )
            # Start monitoring
            await lcu_service.start_monitoring()
            logger.info('LCU service: MONITORING STARTED')
            # Get detailed status
            lcu_details = await lcu_service.get_detailed_status()
            if lcu_details.get('connected'):
                lcu_status = 'connected'
                logger.info('LCU service: CONNECTED TO GAME CLIENT')
            else:
                logger.info('LCU service: WAITING FOR GAME CLIENT')
        else:
            lcu_status = 'failed'
            logger.warning('LCU service: INITIALIZATION FAILED')
    except Exception as e:
        lcu_status = f'error: {e}'
        logger.warning(f'LCU service: WARNING - {e}')
    # Redis service
    redis_status = 'connected'
    try:
        if redis_manager.redis.ping():
            logger.info('Redis service: CONNECTED')
        else:
            redis_status = 'error'
            logger.error('Redis service: ERROR')
    except Exception as e:
        redis_status = f'error: {e}'
        logger.error(f'Redis service: ERROR - {e}')

    logger.info('All services initialized for Windows!')
    logger.info(
        f'Status: Redis={redis_status}, Discord={discord_status}, LCU={lcu_status}'
    )
    await cleanup_service.start_cleanup_service()
    logger.info('Cleanup service: STARTED')


async def cleanup_services():
    """Cleanup all services."""
    try:
        await cleanup_service.stop_cleanup_service()
    except Exception as e:
        logger.error(f'Cleanup service stop error: {e}')
    try:
        await lcu_service.stop_monitoring()
    except Exception as e:
        logger.error(f'LCU cleanup error: {e}')
    try:
        await discord_service.disconnect()
    except Exception as e:
        logger.error(f'Discord cleanup error: {e}')


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
                match_info = {
                    'match_id': match_id,
                    'players': json.dumps(players),
                    'team_data': json.dumps(team_data),
                    'phase': 'ChampSelect',
                    'saved_at': datetime.now(timezone.utc).isoformat()
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
        logger.info(f'Game event received: {event_type}')
        if event_type == 'InProgress':
            await handle_match_start()
        elif event_type == 'EndOfGame':
            await handle_match_end(event_data)
        elif event_type in ('None', 'Lobby'):
            await handle_match_leave(event_data)
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
                    # Save info about joining existing room
                    await voice_service.add_player_to_existing_room(
                        summoner_id,
                        match_id,
                        team_name
                    )
                    # Get channel info for logging
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
    """Handle match start - create voice rooms and auto-assign."""
    try:
        logger.info('Match started - creating voice rooms and auto-assignments')
        # Check current game phase
        try:
            current_phase = (
                await lcu_service.lcu_connector.get_game_flow_phase()
            )
            logger.info(f'Current game phase: {current_phase}')
            if current_phase != 'InProgress':
                logger.info(
                    f'Not creating voice rooms - current phase is '
                    f'{current_phase}, not InProgress'
                )
                return
        except Exception as e:
            logger.warning(f'Could not get game phase: {e}')
            return
        # Get current summoner
        current_summoner = (
            await lcu_service.lcu_connector.get_current_summoner()
        )
        if not current_summoner:
            logger.warning('No current summoner data available')
            return
        summoner_id = str(current_summoner.get('summonerId'))
        summoner_name = current_summoner.get('displayName', 'Unknown')
        logger.info(f'Current summoner: {summoner_name} (ID: {summoner_id})')
        # Get match_id
        match_id = None
        try:
            session = await lcu_service.lcu_connector.get_current_session()
            if session and session.get('gameData', {}).get('gameId'):
                match_id = f"match_{session['gameData']['gameId']}"
                logger.info(f'Match ID from LCU: {match_id}')
        except Exception as e:
            logger.error(f'Failed to get match_id from LCU: {e}')
        if not match_id:
            logger.error('No match_id found, cannot create room')
            return
        # Save current match for this summoner (needed for early-exit cleanup)
        try:
            user_key = f'user:{summoner_id}'
            redis_manager.redis.hset(user_key, 'current_match', match_id)
        except Exception as e:
            logger.warning(f'Failed to save current_match to user key: {e}')

        # Check: If room already exists, don't create new one
        existing_room = voice_service.redis.get_voice_room_by_match(match_id)
        if existing_room:
            logger.info(
                f'Room already exists for match {match_id}: '
                f'{existing_room.get("room_id")}'
            )
            # Check Discord channels
            discord_channels = (
                voice_service.get_voice_room_discord_channels(match_id)
            )
            if not discord_channels or len(discord_channels) == 0:
                logger.warning(
                    f'Room exists but no Discord channels found for '
                    f'match {match_id}'
                )
            else:
                logger.info(
                    f'Discord channels already exist for match {match_id}'
                )
                await auto_assign_player_to_existing_room(
                    summoner_id,
                    match_id,
                    existing_room
                )
                return
        # Create room only if it doesn't exist
        logger.info(f'Creating voice room for match {match_id}')
        # Get team data
        teams_data = await lcu_service.lcu_connector.get_teams()
        blue_team = []
        red_team = []
        all_players = []
        if teams_data:
            blue_team = [
                str(player.get('summonerId'))
                for player in teams_data.get('blue_team', [])
                if player.get('summonerId')
            ]
            red_team = [
                str(player.get('summonerId'))
                for player in teams_data.get('red_team', [])
                if player.get('summonerId')
            ]
            all_players = blue_team + red_team
            logger.info(f'Blue team from LCU: {blue_team}')
            logger.info(f'Red team from LCU: {red_team}')
        else:
            # Fallback: create teams with current player
            all_players = [summoner_id]
            if summoner_id in ['1', '2', '3', '4', '5']:  # demo logic
                blue_team = [summoner_id]
                red_team = []
            else:
                blue_team = [summoner_id]
                red_team = []
            logger.info(
                f'Using fallback teams - Blue: {blue_team}, Red: {red_team}'
            )
        # Create room
        room_result = await voice_service.create_or_get_voice_room(
            match_id,
            all_players,
            {'blue_team': blue_team, 'red_team': red_team}
        )
        if 'error' in room_result:
            logger.error(f'Failed to create room: {room_result["error"]}')
            return
        logger.info(f'Room created successfully: {room_result.get("room_id")}')
        # Get updated room data
        room_data = voice_service.redis.get_voice_room_by_match(match_id)
        if not room_data:
            logger.error(
                f'Room data not found after creation for match {match_id}'
            )
            return
        # Auto-assign user
        await auto_assign_player_to_existing_room(
            summoner_id,
            match_id,
            room_data
        )
    except Exception as e:
        logger.error(f'Error handling match start: {e}')


async def handle_match_end(event_data: dict):
    """Handle match end - cleanup voice rooms with improved cleanup."""
    try:
        logger.info('Match ended - cleaning up voice rooms')
        # Get current summoner to find match info
        current_summoner = (
            await lcu_service.lcu_connector.get_current_summoner()
        )
        match_id = None
        if current_summoner:
            summoner_id = str(current_summoner.get('summonerId'))
            logger.info(f'Current summoner ID: {summoner_id}')
            # Get all matches for this user
            match_keys = []
            try:
                for key in redis_manager.redis.scan_iter(match='user_match:*'):
                    match_keys.append(key)
            except Exception as e:
                logger.error(f'Error scanning match keys: {e}')
            for key in match_keys:
                try:
                    match_info = redis_manager.redis.hgetall(key)
                    if match_info and match_info.get('match_id'):
                        match_id = match_info['match_id']
                        logger.info(f'Found match ID for cleanup: {match_id}')
                        break
                except Exception as e:
                    logger.error(f'Error getting match info from {key}: {e}')
        # If match_id found - clean up
        if match_id:
            logger.info(f'Cleaning up voice room for match {match_id}')
            success = await voice_service.close_voice_room(match_id)
            if success:
                logger.info(
                    f'Successfully cleaned up voice room for match {match_id}'
                )
            else:
                logger.warning(f'Failed to clean up room for match {match_id}')
        else:
            logger.info('Searching for active rooms to cleanup...')
            active_rooms = voice_service.redis.get_all_active_rooms()
            logger.info(f'Found {len(active_rooms)} active rooms')
            for room in active_rooms:
                room_match_id = room.get('match_id')
                if room_match_id:
                    logger.info(f'Cleaning up room for match: {room_match_id}')
                    success = await voice_service.close_voice_room(
                        room_match_id
                    )
                    if success:
                        logger.info(
                            f'Successfully cleaned up room for match '
                            f'{room_match_id}'
                        )
                    else:
                        logger.warning(
                            f'Failed to clean up room for match {room_match_id}'
                        )
        # Clean up user match info
        if current_summoner:
            summoner_id = str(current_summoner.get('summonerId'))
            # Delete all user-related keys
            keys_to_delete = [
                f'user_match:{summoner_id}',
                f'user_invite:{summoner_id}',
                f'user_discord:{summoner_id}'
            ]
            for key in keys_to_delete:
                try:
                    if redis_manager.redis.exists(key):
                        redis_manager.redis.delete(key)
                        logger.info(f'Deleted key: {key}')
                except Exception as e:
                    logger.error(f'Error deleting key {key}: {e}')
    except Exception as e:
        logger.error(f'Error handling match end: {e}')




async def handle_match_leave(event_data: dict):
    """Handle leaving match (e.g., InProgress -> None/Lobby) without full cleanup."""
    try:
        previous_phase = event_data.get('previous_phase')
        new_phase = event_data.get('phase')
        # Only treat as "player left match" when leaving from an active game
        if previous_phase != 'InProgress':
            return
        if new_phase not in ('None', 'Lobby'):
            return

        logger.info(
            f'Player appears to have left the match early (phase {previous_phase} -> {new_phase})'
        )

        # Identify current summoner
        summoner_id = None
        try:
            current_summoner = await lcu_service.lcu_connector.get_current_summoner()
            if current_summoner and current_summoner.get('summonerId'):
                summoner_id = str(current_summoner.get('summonerId'))
        except Exception as e:
            logger.error(f'Failed to get current summoner for leave handling: {e}')

        if not summoner_id:
            logger.warning('Cannot handle leave: summoner_id is unknown')
            return

        user_key = f'user:{summoner_id}'

        # Try to get match_id saved during match start
        match_id = None
        try:
            match_id = redis_manager.redis.hget(user_key, 'current_match')
        except Exception as e:
            logger.error(f'Error reading current_match from user key: {e}')

        # Fallback: find match by scanning active rooms
        if not match_id:
            try:
                active_rooms = voice_service.redis.get_all_active_rooms()
                for room in active_rooms:
                    blue = safe_json_parse(room.get('blue_team'), []) or []
                    red = safe_json_parse(room.get('red_team'), []) or []
                    if summoner_id in blue or summoner_id in red:
                        match_id = room.get('match_id')
                        break
            except Exception as e:
                logger.error(f'Failed to locate match by scanning rooms: {e}')

        if not match_id:
            logger.warning('Cannot handle leave: match_id is unknown')
            return

        # Get Discord user ID
        discord_user_id = None
        try:
            discord_user_id = redis_manager.redis.hget(user_key, 'discord_user_id')
        except Exception as e:
            logger.error(f'Error getting Discord ID: {e}')

        if not discord_user_id:
            logger.warning('Cannot handle leave: discord_user_id not linked')
            return

        await voice_service.handle_player_left_match(
            match_id=match_id,
            summoner_id=summoner_id,
            discord_user_id=int(discord_user_id),
        )

        # Clear current_match on user key (best-effort)
        try:
            redis_manager.redis.hdel(user_key, 'current_match')
        except Exception:
            # If hdel not supported, overwrite with empty string
            try:
                redis_manager.redis.hset(user_key, 'current_match', '')
            except Exception:
                pass

    except Exception as e:
        logger.error(f'Error handling match leave: {e}')
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

# Add demo authentication middleware
if settings.DEMO_AUTH_ENABLED:
    app.add_middleware(DemoAuthMiddleware)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

# Serve static files - FIXED CODE FOR .EXE
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


@app.get('/demo')
async def demo_page():
    """Serve demo page for testing."""
    demo_file = os.path.join(static_dir, 'demo.html')
    if os.path.exists(demo_file):
        return FileResponse(demo_file)
    raise HTTPException(status_code=404, detail='Demo file not found')


@app.get('/link-discord')
async def link_discord_page():
    """Serve Discord linking page (public access)."""
    link_discord_file = os.path.join(static_dir, 'link-discord.html')
    if os.path.exists(link_discord_file):
        return FileResponse(link_discord_file)
    raise HTTPException(status_code=404, detail='Link Discord page not found')


# Include routers
app.include_router(voice.router, prefix='/api')
app.include_router(auth.router, prefix='/api')
app.include_router(lcu.router, prefix='/api')
app.include_router(discord.router, prefix='/api')
app.include_router(demo.router, prefix='/api')


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


@app.get('/auto-token')
async def get_auto_token():
    """Get auto-generated token for demo purposes."""
    if 'auto_auth_token' in globals() and auto_auth_token:
        return {'access_token': auto_auth_token, 'auto_generated': True}
    else:
        raise HTTPException(
            status_code=404,
            detail='No auto-token available'
        )


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
        if redis_manager.redis.ping():
            services['redis'] = 'healthy'
        else:
            services['redis'] = 'unhealthy'
    except Exception as e:
        services['redis'] = f'error: {str(e)}'
    # Discord health
    discord_status = discord_service.get_status()
    if not settings.DISCORD_BOT_TOKEN:
        services['discord'] = 'disabled'
    elif discord_status['connected']:
        services['discord'] = 'connected'
    elif discord_status['mock_mode']:
        services['discord'] = 'mock_mode'
    else:
        services['discord'] = 'disconnected'
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
    elif services['discord'] == 'mock_mode':
        message = 'Application running on Windows! Discord in mock mode.'
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
