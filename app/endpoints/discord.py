import json
import logging
import random
from datetime import datetime, timezone

import discord
import redis
from fastapi import APIRouter, HTTPException, Depends
from pydantic import ValidationError

from app.database import redis_manager
from app.schemas import DiscordLinkRequest
from app.services.discord_service import discord_service
from app.services.lcu_service import lcu_service
from app.services.voice_service import voice_service
from app.utils.security import get_current_user


logger = logging.getLogger(__name__)

router = APIRouter(prefix='/discord', tags=['discord-integration'])


def determine_player_team(summoner_id: str, blue_team: list, red_team: list,
                          demo_mode: bool = False) -> str:
    """Determine which team the player belongs to with improved logic."""
    logger.info(f'Determining team for summoner_id: {summoner_id}')
    logger.info(f'Blue team: {blue_team}')
    logger.info(f'Red team: {red_team}')
    logger.info(f'Demo mode: {demo_mode}')
    # Normalize data types - all IDs should be strings
    summoner_id_str = str(summoner_id)
    blue_team_str = [str(player_id) for player_id in blue_team] \
        if blue_team else []
    red_team_str = [str(player_id) for player_id in red_team] \
        if red_team else []
    logger.info(f'Normalized - Player: {summoner_id_str}')
    logger.info(f'Normalized - Blue: {blue_team_str}')
    logger.info(f'Normalized - Red: {red_team_str}')
    # Detailed check in blue team
    for i, player_id in enumerate(blue_team_str):
        if player_id == summoner_id_str:
            logger.info(f'Player {summoner_id} found in Blue Team at '
                        f'position {i}')
            return 'Blue Team'
    # Detailed check in red team
    for i, player_id in enumerate(red_team_str):
        if player_id == summoner_id_str:
            logger.info(f'Player {summoner_id} found in Red Team at '
                        f'position {i}')
            return 'Red Team'
    # If player not found in any team
    logger.warning(f'Player {summoner_id} not found in any team')
    logger.warning(f'Blue team contains: {blue_team_str}')
    logger.warning(f'Red team contains: {red_team_str}')
    if demo_mode:
        # In demo mode, assign randomly for testing
        team = random.choice(['Blue Team', 'Red Team'])
        logger.info(f'Randomly assigned to {team} in demo mode')
        return team
    else:
        # In real mode - error
        raise HTTPException(
            status_code=400,
            detail=f'Player {summoner_id} not found in match teams. '
                   f'Available teams: Blue={blue_team}, Red={red_team}'
        )


def safe_json_parse(data, default=None):
    """Safely parse JSON data with detailed error logging."""
    if data is None:
        return default
    if isinstance(data, (list, dict)):
        return data
    if isinstance(data, str):
        try:
            return json.loads(data)
        except json.JSONDecodeError as e:
            logger.warning(f'Failed to parse JSON: {data}, error: {e}')
            # Try to parse as comma-separated list
            if ',' in data:
                return [item.strip() for item in data.split(',')
                        if item.strip()]
            return default
    return default


@router.post('/auto-fix-teams')
async def auto_fix_teams_for_match(
    match_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Automatically fix team data for a match using LCU data."""
    try:
        logger.info(f'Auto-fixing teams for match {match_id}')
        # Get current LCU team data
        teams_data = await lcu_service.lcu_connector.get_teams()
        if not teams_data:
            raise HTTPException(status_code=404,
                                detail='No team data from LCU')
        logger.info(f'LCU Teams data for auto-fix: {teams_data}')
        # Extract player IDs
        blue_team_ids = [str(player.get('summonerId'))
                         for player in teams_data.get('blue_team', [])
                         if player.get('summonerId')]
        red_team_ids = [str(player.get('summonerId'))
                        for player in teams_data.get('red_team', [])
                        if player.get('summonerId')]
        logger.info(f'Blue team IDs: {blue_team_ids}')
        logger.info(f'Red team IDs: {red_team_ids}')
        # Get room data
        room_data = voice_service.redis.get_voice_room_by_match(match_id)
        if not room_data:
            raise HTTPException(status_code=404, detail='Room not found')
        # Update room data with correct teams
        room_id = room_data.get('room_id')
        if room_id:
            voice_service.redis.redis.hset(
                f'room:{room_id}',
                mapping={
                    'blue_team': json.dumps(blue_team_ids),
                    'red_team': json.dumps(red_team_ids)
                }
            )
            logger.info(f'Auto-updated room {room_id} with correct teams')
        return {
            'status': 'success',
            'message': 'Teams auto-updated from LCU data',
            'blue_team': blue_team_ids,
            'red_team': red_team_ids,
            'match_id': match_id,
            'auto_fixed': True
        }
    except Exception as e:
        logger.error(f'Auto-fix teams failed: {e}')
        raise HTTPException(status_code=500,
                            detail=f'Auto-fix teams failed: {str(e)}')


@router.post('/auto-assign-team')
async def auto_assign_team(
    match_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Automatically assign user to their actual team based on match data."""
    try:
        logger.info(f'Auto-assign: user {current_user["sub"]} for '
                    f'match {match_id}')
        try:
            # Get current LCU team data
            teams_data = await lcu_service.lcu_connector.get_teams()
            if teams_data:
                logger.info(f'LCU Teams data for auto-fix: {teams_data}')
                # Extract player IDs
                blue_team_ids = [str(player.get('summonerId'))
                                 for player in teams_data.get('blue_team', [])
                                 if player.get('summonerId')]
                red_team_ids = [str(player.get('summonerId'))
                                for player in teams_data.get('red_team', [])
                                if player.get('summonerId')]

                logger.info(f'Blue team IDs: {blue_team_ids}')
                logger.info(f'Red team IDs: {red_team_ids}')
                # Get room data
                room_data = voice_service.redis.get_voice_room_by_match(
                    match_id)
                if room_data:
                    room_id = room_data.get('room_id')
                    if room_id:
                        voice_service.redis.redis.hset(
                            f'room:{room_id}',
                            mapping={
                                'blue_team': json.dumps(blue_team_ids),
                                'red_team': json.dumps(red_team_ids)
                            }
                        )
                        logger.info(f'Auto-updated room {room_id} with '
                                    f'correct teams')
            else:
                logger.warning('No LCU team data available for auto-fix')
        except Exception as e:
            logger.warning(f'Auto-fix teams failed: {e}. '
                           f'Continuing with existing data.')
        # Get match information
        room_data = voice_service.redis.get_voice_room_by_match(match_id)
        if not room_data:
            logger.error(f'Match not found: {match_id}')
            raise HTTPException(status_code=404, detail='Match not found')
        logger.info(f'Room data keys: {list(room_data.keys())}')
        # Get summoner_id of current user
        summoner_id = current_user['sub']
        logger.info(f'Current summoner_id: {summoner_id}')
        # Get team data with safe parsing
        blue_team = safe_json_parse(room_data.get('blue_team'), [])
        red_team = safe_json_parse(room_data.get('red_team'), [])
        logger.info(f'Parsed blue_team: {blue_team} '
                    f'(type: {type(blue_team)})')
        logger.info(f'Parsed red_team: {red_team} '
                    f'(type: {type(red_team)})')
        # If data is empty, check raw_teams_data
        if not blue_team and not red_team and room_data.get('raw_teams_data'):
            logger.info('Checking raw_teams_data for team information')
            raw_teams = safe_json_parse(room_data.get('raw_teams_data'), {})
            if raw_teams:
                blue_team = [str(player.get('summonerId'))
                             for player in raw_teams.get('blue_team', [])
                             if player.get('summonerId')]
                red_team = [str(player.get('summonerId'))
                            for player in raw_teams.get('red_team', [])
                            if player.get('summonerId')]
                logger.info(f'Extracted from raw_teams_data - '
                            f'Blue: {blue_team}, Red: {red_team}')
        # Determine if demo mode or not
        demo_mode = not blue_team and not red_team
        logger.info(f'Demo mode detected: {demo_mode}')
        # If demo mode and no team data, create demo teams
        if demo_mode:
            logger.info('Creating demo teams...')
            all_players = safe_json_parse(room_data.get('players'), [])
            if not all_players:
                all_players = ['test_player', 'player2', 'player3',
                               'player4', 'player5']
                logger.info(f'Using default demo players: {all_players}')
            blue_team = all_players[:3]
            red_team = all_players[3:]
            logger.info(f'Demo blue_team: {blue_team}')
            logger.info(f'Demo red_team: {red_team}')
        # Determine user's actual team
        try:
            user_actual_team = determine_player_team(
                summoner_id, blue_team, red_team, demo_mode)
            logger.info(f'Determined team: {user_actual_team}')
        except HTTPException as e:
            logger.error(f'Failed to determine team: {e.detail}')
            raise
        except Exception as e:
            logger.error(f'Unexpected error in determine_player_team: {e}')
            raise HTTPException(
                status_code=500,
                detail=f'Failed to determine player team: {str(e)}'
            )
        # Get Discord user ID with Redis type error handling
        user_key = f'user:{summoner_id}'
        discord_user_id = None
        try:
            # Try to get as hash first (correct way)
            discord_user_id = redis_manager.redis.hget(
                user_key, 'discord_user_id')
        except redis.exceptions.ResponseError as e:
            if 'WRONGTYPE' in str(e):
                logger.warning(f'Redis key {user_key} has wrong type. '
                               f'Attempting to fix...')
                try:
                    # If it's a string, try to parse it
                    user_data = redis_manager.redis.get(user_key)
                    if user_data:
                        try:
                            user_info = json.loads(user_data)
                            discord_user_id = user_info.get('discord_user_id')
                            logger.info(f'Recovered Discord ID from string '
                                        f'key: {discord_user_id}')
                            # Fix the key by converting to hash
                            redis_manager.redis.delete(user_key)
                            redis_manager.redis.hset(
                                user_key, 'discord_user_id',
                                str(discord_user_id))
                            logger.info('Fixed Redis key type from string '
                                        'to hash')
                        except json.JSONDecodeError:
                            logger.error('Failed to parse user data as JSON: '
                                         f'{user_data}')
                except Exception as parse_error:
                    logger.error(f'Failed to recover Discord ID: {parse_error}')
            else:
                raise e
        if not discord_user_id:
            logger.error(f'Discord account not linked for user {summoner_id}')
            raise HTTPException(
                status_code=400,
                detail='Discord account not linked. Please link your '
                       'Discord account first.'
            )
        logger.info(f'Found Discord user ID: {discord_user_id}')
        # Execute team assignment
        logger.info(f'Assigning user to team: {user_actual_team}')
        # Convert Discord ID to int for Discord API
        try:
            discord_id_int = int(discord_user_id)
        except (ValueError, TypeError) as e:
            logger.error(f'Invalid Discord ID format: {discord_user_id}: {e}')
            raise HTTPException(
                status_code=500,
                detail=f'Invalid Discord ID format: {discord_user_id}'
            )
        success = await discord_service.assign_player_to_team(
            discord_id_int, match_id, user_actual_team
        )
        if success:
            logger.info(f'Successfully auto-assigned user {discord_user_id} '
                        f'to {user_actual_team} in match {match_id}')
            # Get team channel information for returning link
            discord_channels = voice_service.get_voice_room_discord_channels(
                match_id)
            team_channel = None
            if (user_actual_team == 'Blue Team' and discord_channels.get('blue_team')):
                team_channel = discord_channels['blue_team']
            elif (user_actual_team == 'Red Team' and discord_channels.get('red_team')):
                team_channel = discord_channels['red_team']
            response_data = {
                'status': 'success',
                'message': f'Automatically assigned to {user_actual_team}',
                'discord_user_id': discord_user_id,
                'team_name': user_actual_team,
                'match_id': match_id,
                'note': 'You were automatically assigned to your actual '
                        'team based on match data',
                'debug_info': {
                    'summoner_id': summoner_id,
                    'blue_team': blue_team,
                    'red_team': red_team,
                    'demo_mode': demo_mode
                }
            }
            # Add channel information if available
            if team_channel:
                response_data.update({
                    'discord_invite_url': team_channel.get('invite_url'),
                    'discord_channel_name': team_channel.get('channel_name'),
                    'secured': team_channel.get('secured', False)
                })
            logger.info(f'Auto-assign completed successfully: {response_data}')
            return response_data
        else:
            logger.error('Failed to assign user to team in Discord service')
            raise HTTPException(
                status_code=500,
                detail='Failed to assign to team. Make sure the match is '
                       'active and channels are created.'
            )
    except HTTPException:
        logger.error('HTTPException in auto_assign_team')
        raise
    except Exception as e:
        logger.error(f'Unexpected error in auto_assign_team: {e}')
        raise HTTPException(
            status_code=500,
            detail=f'Failed to auto-assign team: {str(e)}'
        )


@router.get('/debug-team-assignment')
async def debug_team_assignment(
    match_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Debug endpoint to see team assignment details."""
    try:
        summoner_id = current_user['sub']
        logger.info(f'DEBUG TEAM ASSIGNMENT for user {summoner_id}')
        # Get room data
        room_data = voice_service.redis.get_voice_room_by_match(match_id)
        if not room_data:
            return {'error': 'Room not found'}
        logger.info(f'RAW ROOM DATA: {room_data}')
        # Parse teams with detailed logging
        blue_team = safe_json_parse(room_data.get('blue_team'), [])
        red_team = safe_json_parse(room_data.get('red_team'), [])

        logger.info(f'PARSED BLUE TEAM: {blue_team} '
                    f'(type: {type(blue_team)})')
        logger.info(f'PARSED RED TEAM: {red_team} '
                    f'(type: {type(red_team)})')
        # Check raw teams data if available
        raw_teams_data = safe_json_parse(room_data.get('raw_teams_data'), {})
        logger.info(f'RAW TEAMS DATA: {raw_teams_data}')
        # Try to determine team
        try:
            team = determine_player_team(summoner_id, blue_team,
                                         red_team, False)
            logger.info(f'DETERMINED TEAM: {team}')
        except Exception as e:
            logger.error(f'Team determination failed: {e}')
            team = 'Error'
        # Check LCU data directly
        lcu_teams = await lcu_service.lcu_connector.get_teams()
        logger.info(f'LCU TEAMS DATA: {lcu_teams}')
        return {
            'summoner_id': summoner_id,
            'room_blue_team': blue_team,
            'room_red_team': red_team,
            'determined_team': team,
            'raw_teams_data': raw_teams_data,
            'lcu_teams': lcu_teams,
            'room_data_keys': list(room_data.keys())
        }
    except Exception as e:
        logger.error(f'Debug failed: {e}')
        return {'error': str(e)}


@router.post('/link-account')
async def link_discord_account(
    request: DiscordLinkRequest,
    current_user: dict = Depends(get_current_user)
):
    """Link Discord account to current LoL user with error handling."""
    try:
        summoner_id = current_user['sub']
        user_key = f'user:{summoner_id}'
        # Use string ID after validation
        discord_user_id_str = request.discord_user_id
        logger.info(f'Starting Discord link process for summoner '
                    f'{summoner_id}')
        logger.info(f'Received Discord ID: "{discord_user_id_str}" '
                    f'(type: {type(discord_user_id_str)})')
        # Check that Discord ID is not empty after validation
        if not discord_user_id_str or not discord_user_id_str.strip():
            raise HTTPException(
                status_code=422,
                detail='Discord ID cannot be empty after validation'
            )
        # Clean Discord ID
        clean_discord_id = ''.join(filter(str.isdigit, discord_user_id_str))
        if len(clean_discord_id) < 17:
            raise HTTPException(
                status_code=422,
                detail=f'Discord ID too short: {len(clean_discord_id)} '
                       f'digits (minimum 17)'
            )
        if len(clean_discord_id) > 20:
            raise HTTPException(
                status_code=422,
                detail=f'Discord ID too long: {len(clean_discord_id)} '
                       f'digits (maximum 20)'
            )
        logger.info(f'Cleaned Discord ID: {clean_discord_id}')
        # Save as hash with correct fields
        user_data = {
            'discord_user_id': clean_discord_id,
            'summoner_id': summoner_id,
            'discord_linked_at': datetime.now(timezone.utc).isoformat(),
            'updated_at': datetime.now(timezone.utc).isoformat()
        }
        # Delete old key and create new one as hash
        logger.info(f'Removing old key: {user_key}')
        redis_manager.redis.delete(user_key)
        logger.info(f'Saving new user data: {user_data}')
        redis_manager.redis.hset(user_key, mapping=user_data)
        redis_manager.redis.expire(user_key, 30 * 24 * 3600)
        # Check that data was saved correctly
        saved_data = redis_manager.redis.hgetall(user_key)
        logger.info(f'Saved user data: {saved_data}')
        if not saved_data.get('discord_user_id'):
            logger.error(f'Failed to save Discord ID. '
                         f'Redis returned: {saved_data}')
            raise HTTPException(
                status_code=500,
                detail='Failed to save Discord ID to database - '
                       'no data saved'
            )
        # Check that saved value matches sent value
        saved_discord_id = saved_data.get('discord_user_id')
        if saved_discord_id != clean_discord_id:
            logger.error(f'Data mismatch! Sent: {clean_discord_id}, '
                         f'Saved: {saved_discord_id}')
            raise HTTPException(
                status_code=500,
                detail=f'Data corruption: sent {clean_discord_id} but '
                       f'saved {saved_discord_id}'
            )
        logger.info(f'Successfully linked Discord account {clean_discord_id} '
                    f'to summoner {summoner_id}')
        return {
            'status': 'success',
            'message': 'Discord account linked successfully',
            'discord_user_id': clean_discord_id,
            'summoner_id': summoner_id,
            'saved_correctly': True,
            'saved_value': saved_discord_id,
            'debug': {
                'received_type': type(request.discord_user_id).__name__,
                'cleaned_value': clean_discord_id,
                'redis_saved_value': saved_discord_id
            }
        }
    except HTTPException:
        raise
    except ValidationError as e:
        logger.error(f'Pydantic validation error in link_discord_account: {e}')
        logger.error(f'Error details: {e.errors() if hasattr(e, "errors") else str(e)}')
        raise HTTPException(
            status_code=422,
            detail={
                'type': 'validation_error',
                'message': str(e),
                'errors': e.errors() if hasattr(e, 'errors') else None
            }
        )
    except Exception as e:
        logger.error(f'Unexpected error in link_discord_account: {e}')
        logger.error(f'Error type: {type(e).__name__}')
        import traceback
        logger.error(f'Stack trace: {traceback.format_exc()}')
        raise HTTPException(
            status_code=500,
            detail={
                'type': 'unexpected_error',
                'message': f'Failed to link Discord account: {str(e)}',
                'error_type': type(e).__name__
            }
        )


@router.get('/linked-account')
async def get_linked_discord_account(
    current_user: dict = Depends(get_current_user)
):
    """Get linked Discord account information with Redis handling."""
    try:
        summoner_id = current_user['sub']
        user_key = f'user:{summoner_id}'
        logger.info(f'Getting linked account for summoner: {summoner_id}')
        # Get data as hash
        user_data = redis_manager.redis.hgetall(user_key)
        logger.info(f'Raw Redis data for {user_key}: {user_data}')
        discord_user_id = user_data.get('discord_user_id')
        if not discord_user_id:
            # Check if key saved in old format (string)
            try:
                old_format_data = redis_manager.redis.get(user_key)
                if old_format_data:
                    logger.warning(f'Found old format data for {user_key}: '
                                   f'{old_format_data}')
                    try:
                        # Try to parse as JSON
                        parsed_data = json.loads(old_format_data)
                        discord_user_id = parsed_data.get('discord_user_id')
                        if discord_user_id:
                            logger.info(f'Converting old format to hash '
                                        f'for {user_key}')
                            # Convert to hash format
                            redis_manager.redis.delete(user_key)
                            new_data = {
                                'discord_user_id': str(discord_user_id),
                                'summoner_id': summoner_id,
                                'converted_at': datetime.now(
                                    timezone.utc).isoformat()
                            }
                            redis_manager.redis.hset(user_key, mapping=new_data)
                            redis_manager.redis.expire(user_key,
                                                       30 * 24 * 3600)
                    except json.JSONDecodeError:
                        # If not JSON, maybe it's just a string with ID
                        discord_user_id = old_format_data
                        logger.info(f'Converting string ID to hash '
                                    f'for {user_key}')
                        redis_manager.redis.delete(user_key)
                        new_data = {
                            'discord_user_id': str(discord_user_id),
                            'summoner_id': summoner_id,
                            'converted_at': datetime.now(
                                timezone.utc).isoformat()
                        }
                        redis_manager.redis.hset(user_key, mapping=new_data)
                        redis_manager.redis.expire(user_key, 30 * 24 * 3600)
            except Exception as e:
                logger.error(f'Error checking old format: {e}')
        return {
            'summoner_id': summoner_id,
            'discord_user_id': discord_user_id,
            'linked': discord_user_id is not None,
            'data_source': 'hash' if user_data else 'old_format'
        }
    except Exception as e:
        logger.error(f'Failed to get linked account: {e}')
        raise HTTPException(
            status_code=500,
            detail=f'Failed to get linked account: {str(e)}'
        )


@router.delete('/unlink-account')
async def unlink_discord_account(
    current_user: dict = Depends(get_current_user)
):
    """Unlink Discord account from LoL summoner."""
    try:
        user_key = f'user:{current_user["sub"]}'
        redis_manager.redis.delete(user_key)
        logger.info(f'Unlinked Discord account for summoner '
                    f'{current_user["sub"]}')
        return {
            'status': 'success',
            'message': 'Discord account unlinked successfully'
        }
    except Exception as e:
        logger.error(f'Failed to unlink Discord account: {e}')
        raise HTTPException(
            status_code=500,
            detail=f'Failed to unlink Discord account: {str(e)}'
        )


@router.get('/status')
async def get_discord_status():
    """Get Discord service status."""
    try:
        status = discord_service.get_status()
        return {
            'status': 'success',
            'discord_service': status
        }
    except Exception as e:
        logger.error(f'Failed to get Discord status: {e}')
        raise HTTPException(
            status_code=500,
            detail=f'Failed to get Discord status: {str(e)}'
        )


@router.get('/user-info')
async def get_discord_user_info(
    discord_user_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get information about Discord user."""
    try:
        # This is a mock
        user_exists = True  # Assume user exists for demo purposes
        return {
            'status': 'success',
            'discord_user_id': discord_user_id,
            'user_exists': user_exists,
            'note': 'This is a mock response. In production, would '
                    'verify user exists in Discord guild.'
        }
    except Exception as e:
        logger.error(f'Failed to get Discord user info: {e}')
        raise HTTPException(
            status_code=500,
            detail=f'Failed to get Discord user info: {str(e)}'
        )


@router.post('/admin/fix-redis-keys')
async def fix_redis_keys(current_user: dict = Depends(get_current_user)):
    """Admin endpoint to fix Redis key type issues."""
    try:
        redis_manager.fix_redis_key_types()
        return {
            'status': 'success',
            'message': 'Redis key type fix completed'
        }
    except Exception as e:
        logger.error(f'Failed to fix Redis keys: {e}')
        raise HTTPException(
            status_code=500,
            detail=f'Failed to fix Redis keys: {str(e)}'
        )


@router.post('/emergency-fix-teams')
async def emergency_fix_teams(
    match_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Emergency fix for team assignment - set teams based on LCU data."""
    try:
        logger.info(f'EMERGENCY FIX for match {match_id}')
        # Get current LCU team data
        teams_data = await lcu_service.lcu_connector.get_teams()
        if not teams_data:
            raise HTTPException(status_code=404,
                                detail='No team data from LCU')
        logger.info(f'LCU Teams data: {teams_data}')
        # Extract player IDs
        blue_team_ids = [str(player.get('summonerId'))
                         for player in teams_data.get('blue_team', [])
                         if player.get('summonerId')]
        red_team_ids = [str(player.get('summonerId'))
                        for player in teams_data.get('red_team', [])
                        if player.get('summonerId')]
        logger.info(f'Blue team IDs: {blue_team_ids}')
        logger.info(f'Red team IDs: {red_team_ids}')
        # Get room data
        room_data = voice_service.redis.get_voice_room_by_match(match_id)
        if not room_data:
            raise HTTPException(status_code=404, detail='Room not found')
        # Update room data with correct teams
        room_id = room_data.get('room_id')
        if room_id:
            voice_service.redis.redis.hset(
                f'room:{room_id}',
                mapping={
                    'blue_team': json.dumps(blue_team_ids),
                    'red_team': json.dumps(red_team_ids)
                }
            )
            logger.info(f'Updated room {room_id} with correct teams')
        return {
            'status': 'success',
            'message': 'Teams updated from LCU data',
            'blue_team': blue_team_ids,
            'red_team': red_team_ids,
            'match_id': match_id
        }
    except Exception as e:
        logger.error(f'Emergency fix failed: {e}')
        raise HTTPException(status_code=500,
                            detail=f'Emergency fix failed: {str(e)}')


@router.get('/user-server-status/{discord_user_id}')
async def check_user_server_status(
    discord_user_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Check if user is on Discord server and bot has permissions."""
    try:
        status = {
            'discord_user_id': discord_user_id,
            'on_server': False,
            'bot_has_permissions': False,
            'can_assign_roles': False,
            'server_invite_available': False
        }
        if not discord_service.connected or not discord_service.guild:
            return status
        # Check if user is on server
        try:
            # Convert to int for Discord API
            discord_id_int = int(discord_user_id)
            member = discord_service.guild.get_member(discord_id_int)
            if not member:
                try:
                    member = await discord_service.guild.fetch_member(
                        discord_id_int)
                except discord.NotFound:
                    status['on_server'] = False
                except discord.Forbidden:
                    status['on_server'] = 'unknown'
            else:
                status['on_server'] = True
        except (ValueError, TypeError) as e:
            logger.error(f'Invalid Discord ID format: {discord_user_id}: {e}')
            status['on_server'] = 'invalid_id'
        except Exception as e:
            logger.error(f'Error checking member status: {e}')
        # Check bot permissions
        if discord_service.guild.me:
            status['bot_has_permissions'] = True
            status['can_assign_roles'] = \
                discord_service.guild.me.guild_permissions.manage_roles
        # Check if there's a server invite
        invite_key = f'server_invite:{discord_user_id}'
        server_invite = redis_manager.redis.get(invite_key)
        if server_invite:
            status['server_invite_available'] = True
            status['server_invite'] = server_invite
        return status
    except Exception as e:
        logger.error(f'Failed to check user server status: {e}')
        raise HTTPException(
            status_code=500,
            detail=f'Failed to check user status: {str(e)}'
        )


@router.get('/user-match-info/{summoner_id}')
async def get_user_match_info(
    summoner_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get user's current match and voice channel information."""
    try:
        # Get user's match information
        match_info_key = f'user_match:{summoner_id}'
        match_info = redis_manager.redis.hgetall(match_info_key)
        if not match_info:
            return {'match_id': None}
        match_id = match_info.get('match_id')
        if not match_id:
            return {'match_id': None}
        # Get voice room information
        room_data = voice_service.redis.get_voice_room_by_match(match_id)
        if not room_data:
            return {'match_id': match_id, 'voice_channel': None}
        # Determine user's team
        blue_team = safe_json_parse(room_data.get('blue_team'), [])
        red_team = safe_json_parse(room_data.get('red_team'), [])
        team_name = None
        if summoner_id in blue_team:
            team_name = 'Blue Team'
        elif summoner_id in red_team:
            team_name = 'Red Team'
        # Get Discord channel information
        discord_channels = voice_service.get_voice_room_discord_channels(
            match_id)
        voice_channel = None
        if team_name == 'Blue Team' and discord_channels.get('blue_team'):
            voice_channel = discord_channels['blue_team']
        elif team_name == 'Red Team' and discord_channels.get('red_team'):
            voice_channel = discord_channels['red_team']
        return {
            'match_id': match_id,
            'team_name': team_name,
            'voice_channel': voice_channel
        }
    except Exception as e:
        logger.error(f'Failed to get user match info: {e}')
        raise HTTPException(
            status_code=500,
            detail=f'Failed to get user match info: {str(e)}'
        )


@router.get('/match-status/{summoner_id}')
async def get_match_status(
    summoner_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get user's current match status."""
    try:
        # Get user's match information
        match_info_key = f'user_match:{summoner_id}'
        # Try to get as hash (new way)
        match_info = redis_manager.redis.hgetall(match_info_key)
        if not match_info:
            # Fallback: try to get as string (old way)
            match_info_data = redis_manager.redis.get(match_info_key)
            if match_info_data:
                try:
                    match_info = json.loads(match_info_data)
                except json.JSONDecodeError:
                    match_info = {}
        match_id = match_info.get('match_id') if match_info else None
        # If match_id not found, try to get it from LCU
        if not match_id:
            try:
                # Check if LCU is connected
                if lcu_service.lcu_connector.is_connected():
                    # Get current phase
                    phase = await lcu_service.lcu_connector.get_game_flow_phase()
                    logger.info(f'Current phase from LCU: {phase}')
                    # If phase is InProgress, get match data
                    if phase == 'InProgress':
                        session = await lcu_service.lcu_connector.get_current_session()
                        if session and session.get('gameData', {}).get('gameId'):
                            match_id = f'match_{session["gameData"]["gameId"]}'
                            logger.info(f'Found match_id from LCU: {match_id}')
                            # Save match_id for user
                            redis_manager.redis.hset(match_info_key,
                                                     'match_id', match_id)
                            redis_manager.redis.expire(match_info_key, 3600)
            except Exception as e:
                logger.error(f'Error getting match_id from LCU: {e}')
        if not match_id:
            return {
                'match_id': None,
                'match_started': False,
                'in_champ_select': False,
                'in_loading_screen': False,
                'in_progress': False,
                'voice_channel': None
            }
        # Get voice room information
        room_data = voice_service.redis.get_voice_room_by_match(match_id)
        # If room not found but game is in progress, create room
        if not room_data:
            try:
                # Check if LCU is connected
                if lcu_service.lcu_connector.is_connected():
                    phase = await lcu_service.lcu_connector.get_game_flow_phase()
                    logger.info(f'Current phase for room creation: {phase}')
                    if phase == 'InProgress':
                        # Try to get team data
                        teams_data = await lcu_service.lcu_connector.get_teams()
                        if teams_data:
                            blue_team_ids = [str(player.get('summonerId'))
                                             for player in
                                             teams_data.get('blue_team', [])
                                             if player.get('summonerId')]
                            red_team_ids = [str(player.get('summonerId'))
                                            for player in
                                            teams_data.get('red_team', [])
                                            if player.get('summonerId')]
                            all_players = blue_team_ids + red_team_ids
                            logger.info(f'Blue team IDs from LCU: '
                                        f'{blue_team_ids}')
                            logger.info(f'Red team IDs from LCU: '
                                        f'{red_team_ids}')
                            if all_players:
                                # Create voice room
                                room_result = await voice_service.create_or_get_voice_room(
                                    match_id,
                                    all_players,
                                    {'blue_team': blue_team_ids,
                                     'red_team': red_team_ids}
                                )
                                logger.info(f'Created room from match-status: '
                                            f'{room_result}')
                                # Update room_data
                                room_data = voice_service.redis.get_voice_room_by_match(
                                    match_id)
                                if room_data:
                                    logger.info(f'Room created successfully: '
                                                f'{room_data.get("room_id")}')
                                else:
                                    logger.error('Room still not found '
                                                 'after creation!')
                            else:
                                logger.warning('No player data from LCU for '
                                               'room creation')
                        else:
                            logger.warning('No team data from LCU for '
                                           'room creation')
                    else:
                        logger.info(f'Not creating room - current phase is '
                                    f'{phase}, not InProgress')
                else:
                    logger.warning('LCU not connected, cannot create room')
            except Exception as e:
                logger.error(f'Error creating room from match-status: {e}')
                import traceback
                logger.error(f'Stack trace: {traceback.format_exc()}')
        if not room_data:
            logger.warning(f'No room data found for match {match_id}')
            return {
                'match_id': match_id,
                'match_started': False,
                'in_champ_select': False,
                'in_loading_screen': False,
                'in_progress': False,
                'voice_channel': None
            }
        try:
            game_phase = await lcu_service.lcu_connector.get_game_flow_phase()
            # Determine exact phases
            in_champ_select = game_phase == 'ChampSelect'
            in_loading_screen = game_phase == 'LoadingScreen'
            in_progress = game_phase == 'InProgress'
            logger.info(f'Current game phase: {game_phase} - '
                        f'ChampSelect: {in_champ_select}, '
                        f'Loading: {in_loading_screen}, '
                        f'InProgress: {in_progress}')
        except Exception as e:
            logger.warning(f'Could not get game phase from LCU: {e}')
            # Fallback logic
            in_champ_select = not room_data.get('match_started')
            in_loading_screen = False
            in_progress = room_data.get('match_started') == 'true'
        # RETURN VOICE CHANNEL ONLY WHEN MATCH HAS STARTED (InProgress)
        if not in_progress:
            return {
                'match_id': match_id,
                'match_started': False,
                'in_champ_select': in_champ_select,
                'in_loading_screen': in_loading_screen,
                'in_progress': False,
                'voice_channel': None
            }
        # Only when match is InProgress - determine team and return channel
        blue_team = safe_json_parse(room_data.get('blue_team'), [])
        red_team = safe_json_parse(room_data.get('red_team'), [])
        team_name = None
        if summoner_id in blue_team:
            team_name = 'Blue Team'
        elif summoner_id in red_team:
            team_name = 'Red Team'
        else:
            # If user not in any team, don't return channel
            logger.warning(f'User {summoner_id} not found in any team '
                           f'for match {match_id}')
            logger.info(f'Blue team: {blue_team}')
            logger.info(f'Red team: {red_team}')
            return {
                'match_id': match_id,
                'match_started': True,
                'in_champ_select': False,
                'in_loading_screen': False,
                'in_progress': True,
                'voice_channel': None,
                'team_name': None
            }
        # Get Discord channel information
        discord_channels = voice_service.get_voice_room_discord_channels(
            match_id)
        voice_channel = None
        if team_name == 'Blue Team' and discord_channels.get('blue_team'):
            voice_channel = discord_channels['blue_team']
        elif team_name == 'Red Team' and discord_channels.get('red_team'):
            voice_channel = discord_channels['red_team']
        return {
            'match_id': match_id,
            'match_started': True,
            'in_champ_select': False,
            'in_loading_screen': False,
            'in_progress': True,
            'team_name': team_name,
            'voice_channel': voice_channel
        }
    except Exception as e:
        logger.error(f'Failed to get match status: {e}')
        raise HTTPException(
            status_code=500,
            detail=f'Failed to get match status: {str(e)}'
        )


@router.post('/force-update-discord-id')
async def force_update_discord_id(
    new_discord_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Force update Discord ID and prevent overwriting."""
    try:
        summoner_id = current_user['sub']
        user_key = f'user:{summoner_id}'
        # Get current data
        current_data = redis_manager.redis.hgetall(user_key)
        logger.info(f'Current user data before update: {current_data}')
        # Update ONLY Discord ID, keeping other fields
        update_data = {
            'discord_user_id': str(new_discord_id),
            'updated_at': datetime.now(timezone.utc).isoformat(),
            'force_updated': 'true'
        }
        # Update only needed fields
        redis_manager.redis.hset(user_key, mapping=update_data)
        # Check result
        updated_data = redis_manager.redis.hgetall(user_key)
        logger.info(f'Updated user data: {updated_data}')
        return {
            'status': 'success',
            'message': f'Discord ID force updated to {new_discord_id}',
            'previous_discord_id': current_data.get('discord_user_id'),
            'new_discord_id': new_discord_id,
            'updated_data': updated_data
        }
    except Exception as e:
        logger.error(f'Force update failed: {e}')
        raise HTTPException(
            status_code=500,
            detail=f'Force update failed: {str(e)}'
        )


@router.post('/clear-redis-data')
async def clear_redis_data_for_user(
    current_user: dict = Depends(get_current_user)
):
    """Clear all Redis data for current user to fix corruption."""
    try:
        summoner_id = current_user['sub']
        # Delete all possible keys for this user
        keys_to_delete = [
            f'user:{summoner_id}',
            f'user_discord:{summoner_id}',
            f'user_match:{summoner_id}',
            f'user_invite:{summoner_id}'
        ]
        deleted_count = 0
        for key in keys_to_delete:
            if redis_manager.redis.exists(key):
                redis_manager.redis.delete(key)
                deleted_count += 1
                logger.info(f'Deleted Redis key: {key}')
        return {
            'status': 'success',
            'message': f'Cleared {deleted_count} Redis keys for user',
            'summoner_id': summoner_id,
            'deleted_keys': keys_to_delete
        }
    except Exception as e:
        logger.error(f'Failed to clear Redis data: {e}')
        raise HTTPException(
            status_code=500,
            detail=f'Failed to clear Redis data: {str(e)}'
        )


@router.get('/debug-user-data')
async def debug_user_data(
    current_user: dict = Depends(get_current_user)
):
    """Debug endpoint to see all user data in Redis."""
    try:
        summoner_id = current_user['sub']
        keys_to_check = [
            f'user:{summoner_id}',
            f'user_discord:{summoner_id}',
            f'user_match:{summoner_id}',
            f'user_invite:{summoner_id}'
        ]
        debug_info = {}
        for key in keys_to_check:
            key_type = redis_manager.redis.type(key)
            debug_info[key] = {
                'exists': redis_manager.redis.exists(key),
                'type': key_type,
                'data': None
            }
            if key_type == 'hash':
                debug_info[key]['data'] = redis_manager.redis.hgetall(key)
            elif key_type == 'string':
                debug_info[key]['data'] = redis_manager.redis.get(key)
            elif key_type == 'list':
                debug_info[key]['data'] = redis_manager.redis.lrange(key,
                                                                     0, -1)
        return {
            'summoner_id': summoner_id,
            'debug_info': debug_info
        }
    except Exception as e:
        logger.error(f'Debug user data failed: {e}')
        raise HTTPException(
            status_code=500,
            detail=f'Debug failed: {str(e)}'
        )


@router.get('/debug-guild-info')
async def debug_guild_info(current_user: dict = Depends(get_current_user)):
    """Debug endpoint to get detailed guild information."""
    try:
        if not discord_service.connected or not discord_service.guild:
            return {'error': 'Discord not connected'}
        guild = discord_service.guild
        bot_member = guild.me
        # Get role information
        roles_info = []
        for role in guild.roles:
            roles_info.append({
                'name': role.name,
                'id': str(role.id),
                'position': role.position,
                'permissions': role.permissions.value,
                'is_bot_role': role == bot_member.top_role
            })
        # Get member count information
        members = guild.members
        member_sample = [{'id': str(m.id), 'name': m.display_name}
                         for m in members[:5]]
        return {
            'guild_name': guild.name,
            'guild_id': str(guild.id),
            'member_count': guild.member_count,
            'bot_permissions': {
                'manage_roles': bot_member.guild_permissions.manage_roles,
                'manage_channels': bot_member.guild_permissions.manage_channels,
                'view_channel': bot_member.guild_permissions.view_channel,
                'administrator': bot_member.guild_permissions.administrator
            },
            'bot_top_role': {
                'name': bot_member.top_role.name,
                'position': bot_member.top_role.position
            },
            'roles': roles_info,
            'member_sample': member_sample,
            'available_guilds': [
                {'name': g.name, 'id': str(g.id)}
                for g in discord_service.client.guilds
            ] if discord_service.client else []
        }
    except Exception as e:
        logger.error(f'Failed to get guild debug info: {e}')
        raise HTTPException(
            status_code=500,
            detail=f'Failed to get guild info: {str(e)}'
        )


@router.get('/search-user/{discord_user_id}')
async def search_discord_user(
    discord_user_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Search for a specific user in Discord guild."""
    try:
        if not discord_service.connected or not discord_service.guild:
            return {'error': 'Discord not connected'}
        guild = discord_service.guild
        # Convert to int for Discord API
        try:
            discord_id_int = int(discord_user_id)
        except (ValueError, TypeError) as e:
            return {
                'searched_user_id': discord_user_id,
                'error': f'Invalid Discord ID format: {discord_user_id}: {e}'
            }
        # Method 1: Check cache
        member_cache = guild.get_member(discord_id_int)
        # Method 2: Try to fetch from API
        member_fetched = None
        try:
            member_fetched = await guild.fetch_member(discord_id_int)
        except discord.NotFound:
            pass
        except Exception as e:
            logger.error(f'Error fetching member: {e}')
        # Method 3: Iterate through members
        member_iter = None
        for m in guild.members:
            if m.id == discord_id_int:
                member_iter = m
                break
        return {
            'searched_user_id': discord_user_id,
            'searched_user_id_int': discord_id_int,
            'in_cache': member_cache is not None,
            'in_api': member_fetched is not None,
            'in_iteration': member_iter is not None,
            'cache_info': {
                'name': member_cache.display_name if member_cache else None,
                'roles': [r.name for r in member_cache.roles]
                if member_cache else []
            } if member_cache else None,
            'guild_info': {
                'name': guild.name,
                'id': str(guild.id),
                'total_members': guild.member_count,
                'cached_members': len(guild.members)
            }
        }
    except Exception as e:
        logger.error(f'Failed to search user: {e}')
        raise HTTPException(
            status_code=500,
            detail=f'Failed to search user: {str(e)}'
        )


@router.get('/list-server-members')
async def list_server_members(
    current_user: dict = Depends(get_current_user)
):
    """Get all members from Discord server for debugging."""
    try:
        if not discord_service.connected or not discord_service.guild:
            return {'error': 'Discord not connected'}
        guild = discord_service.guild
        members_info = []
        for member in guild.members:
            if not member.bot:  # Skip bots
                members_info.append({
                    'id': str(member.id),
                    'name': member.display_name,
                    'username': member.name,
                    'discriminator': getattr(member, 'discriminator', '0'),
                    'bot': member.bot,
                    'status': str(member.status)
                    if hasattr(member, 'status') else 'unknown'
                })
        return {
            'total_members': len(members_info),
            'members': members_info
        }
    except Exception as e:
        logger.error(f'Failed to list server members: {e}')
        raise HTTPException(
            status_code=500,
            detail=f'Failed to list members: {str(e)}'
        )


@router.post('/test-id-transfer')
async def test_discord_id_transfer(
    test_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """Test endpoint to check Discord ID transfer precision."""
    received_id = test_data.get('discord_user_id')
    return {
        'received_type': type(received_id).__name__,
        'received_value': received_id,
        'received_raw': str(received_id),
        'as_int': int(received_id) if isinstance(
            received_id, (int, str)) and str(received_id).isdigit() else None,
        'as_str': str(received_id),
        'precision_lost': str(received_id) != '262175818275356672'
        if received_id else None
    }


@router.post('/debug-link')
async def debug_discord_link(
    debug_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """Debug endpoint for Discord linking issues."""
    try:
        received_data = debug_data.get('discord_user_id')
        return {
            'received_type': type(received_data).__name__,
            'received_value': received_data,
            'expected_type': 'str',
            'summoner_id': current_user['sub'],
            'note': 'This endpoint helps debug data transfer issues'
        }
    except Exception as e:
        logger.error(f'Debug link error: {e}')
        raise HTTPException(status_code=500, detail=str(e))


@router.post('/test-validation')
async def test_validation(
    test_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """Test endpoint to validate Discord ID without saving."""
    try:
        # Create temporary request for validation
        from app.schemas import DiscordLinkRequest
        # Use Pydantic for validation
        validated_data = DiscordLinkRequest(**test_data)
        return {
            'status': 'success',
            'validated_data': {
                'discord_user_id': validated_data.discord_user_id,
                'type': type(validated_data.discord_user_id).__name__
            },
            'raw_input': test_data,
            'note': 'This is only validation test - no data saved'
        }
    except ValidationError as e:
        logger.error(f'Validation error in test: {e}')
        return {
            'status': 'validation_error',
            'errors': e.errors(),
            'raw_input': test_data
        }
    except Exception as e:
        logger.error(f'Error in test validation: {e}')
        return {
            'status': 'error',
            'message': str(e),
            'raw_input': test_data
        }
