import logging
import json
import random
import redis
from fastapi import APIRouter, HTTPException, Depends
from app.services.discord_service import discord_service
from app.services.lcu_service import lcu_service
from app.utils.security import get_current_user
from app.database import redis_manager
from app.schemas import DiscordLinkRequest, DiscordAssignRequest
from app.services.voice_service import voice_service
from datetime import datetime, timezone

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/discord", tags=["discord-integration"])


def determine_player_team(summoner_id: str, blue_team: list, red_team: list, demo_mode: bool = False) -> str:
    """Determine which team the player belongs to with improved logic."""
    logger.info(f"🔍 Determining team for summoner_id: {summoner_id}")
    logger.info(f"🔵 Blue team: {blue_team}")
    logger.info(f"🔴 Red team: {red_team}")
    logger.info(f"🎮 Demo mode: {demo_mode}")
    
    # Нормализуем типы данных - все ID должны быть строками
    summoner_id_str = str(summoner_id)
    blue_team_str = [str(player_id) for player_id in blue_team] if blue_team else []
    red_team_str = [str(player_id) for player_id in red_team] if red_team else []
    
    logger.info(f"🔄 Normalized - Player: {summoner_id_str}")
    logger.info(f"🔄 Normalized - Blue: {blue_team_str}")
    logger.info(f"🔄 Normalized - Red: {red_team_str}")
    
    # Детальная проверка в синей команде
    for i, player_id in enumerate(blue_team_str):
        if player_id == summoner_id_str:
            logger.info(f"✅ Player {summoner_id} found in Blue Team at position {i}")
            return "Blue Team"
    
    # Детальная проверка в красной команде  
    for i, player_id in enumerate(red_team_str):
        if player_id == summoner_id_str:
            logger.info(f"✅ Player {summoner_id} found in Red Team at position {i}")
            return "Red Team"
    
    # Если игрок не найден в командах
    logger.warning(f"⚠️ Player {summoner_id} not found in any team")
    logger.warning(f"🔍 Blue team contains: {blue_team_str}")
    logger.warning(f"🔍 Red team contains: {red_team_str}")
    
    if demo_mode:
        # В демо-режиме назначаем случайно для тестирования
        team = random.choice(["Blue Team", "Red Team"])
        logger.info(f"🎲 Randomly assigned to {team} in demo mode")
        return team
    else:
        # В реальном режиме - ошибка
        raise HTTPException(
            status_code=400,
            detail=f"Player {summoner_id} not found in match teams. Available teams: Blue={blue_team}, Red={red_team}"
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
            logger.warning(f"⚠️ Failed to parse JSON: {data}, error: {e}")
            # Попробуем разобрать как список, разделенный запятыми
            if ',' in data:
                return [item.strip() for item in data.split(',') if item.strip()]
            return default
    return default


@router.post("/auto-fix-teams")
async def auto_fix_teams_for_match(
    match_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Automatically fix team data for a match using LCU data."""
    try:
        logger.info(f"🔄 Auto-fixing teams for match {match_id}")
        
        # Get current LCU team data
        teams_data = await lcu_service.lcu_connector.get_teams()
        if not teams_data:
            raise HTTPException(status_code=404, detail="No team data from LCU")
        
        logger.info(f"🎯 LCU Teams data for auto-fix: {teams_data}")
        
        # Extract player IDs
        blue_team_ids = [str(player.get('summonerId')) for player in teams_data.get('blue_team', []) if player.get('summonerId')]
        red_team_ids = [str(player.get('summonerId')) for player in teams_data.get('red_team', []) if player.get('summonerId')]
        
        logger.info(f"🔵 Blue team IDs: {blue_team_ids}")
        logger.info(f"🔴 Red team IDs: {red_team_ids}")
        
        # Get room data
        room_data = voice_service.redis.get_voice_room_by_match(match_id)
        if not room_data:
            raise HTTPException(status_code=404, detail="Room not found")
        
        # Update room data with correct teams
        room_id = room_data.get('room_id')
        if room_id:
            voice_service.redis.redis.hset(
                f"room:{room_id}",
                mapping={
                    'blue_team': json.dumps(blue_team_ids),
                    'red_team': json.dumps(red_team_ids)
                }
            )
            logger.info(f"✅ Auto-updated room {room_id} with correct teams")
        
        return {
            "status": "success",
            "message": "Teams auto-updated from LCU data",
            "blue_team": blue_team_ids,
            "red_team": red_team_ids,
            "match_id": match_id,
            "auto_fixed": True
        }
        
    except Exception as e:
        logger.error(f"❌ Auto-fix teams failed: {e}")
        raise HTTPException(status_code=500, detail=f"Auto-fix teams failed: {str(e)}")


@router.post("/auto-assign-team")
async def auto_assign_team(
    match_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Automatically assign user to their actual team based on match data with automatic team data fix."""
    try:
        logger.info(f"🎯 Auto-assign: user {current_user['sub']} for match {match_id}")

        # === АВТОМАТИЧЕСКОЕ ИСПРАВЛЕНИЕ ДАННЫХ КОМАНД ИЗ LCU ===
        try:
            # Get current LCU team data
            teams_data = await lcu_service.lcu_connector.get_teams()
            if teams_data:
                logger.info(f"🎯 LCU Teams data for auto-fix: {teams_data}")
                
                # Extract player IDs
                blue_team_ids = [str(player.get('summonerId')) for player in teams_data.get('blue_team', []) if player.get('summonerId')]
                red_team_ids = [str(player.get('summonerId')) for player in teams_data.get('red_team', []) if player.get('summonerId')]
                
                logger.info(f"🔵 Blue team IDs: {blue_team_ids}")
                logger.info(f"🔴 Red team IDs: {red_team_ids}")
                
                # Get room data
                room_data = voice_service.redis.get_voice_room_by_match(match_id)
                if room_data:
                    room_id = room_data.get('room_id')
                    if room_id:
                        voice_service.redis.redis.hset(
                            f"room:{room_id}",
                            mapping={
                                'blue_team': json.dumps(blue_team_ids),
                                'red_team': json.dumps(red_team_ids)
                            }
                        )
                        logger.info(f"✅ Auto-updated room {room_id} with correct teams")
            else:
                logger.warning("⚠️ No LCU team data available for auto-fix")
        except Exception as e:
            logger.warning(f"⚠️ Auto-fix teams failed: {e}. Continuing with existing data.")
        # === КОНЕЦ АВТОИСПРАВЛЕНИЯ ===

        # Получаем информацию о матче (теперь с исправленными данными)
        room_data = voice_service.redis.get_voice_room_by_match(match_id)
        if not room_data:
            logger.error(f"❌ Match not found: {match_id}")
            raise HTTPException(status_code=404, detail="Match not found")

        logger.info(f"📊 Room data keys: {list(room_data.keys())}")

        # Получаем summoner_id текущего пользователя
        summoner_id = current_user['sub']
        logger.info(f"👤 Current summoner_id: {summoner_id}")

        # Получаем данные о командах с безопасным парсингом
        blue_team = safe_json_parse(room_data.get('blue_team'), [])
        red_team = safe_json_parse(room_data.get('red_team'), [])
        
        logger.info(f"🔵 Parsed blue_team: {blue_team} (type: {type(blue_team)})")
        logger.info(f"🔴 Parsed red_team: {red_team} (type: {type(red_team)})")

        # Если данные пустые, проверяем raw_teams_data
        if not blue_team and not red_team and room_data.get('raw_teams_data'):
            logger.info("🔄 Checking raw_teams_data for team information")
            raw_teams = safe_json_parse(room_data.get('raw_teams_data'), {})
            if raw_teams:
                blue_team = [str(player.get('summonerId')) for player in raw_teams.get('blue_team', []) if player.get('summonerId')]
                red_team = [str(player.get('summonerId')) for player in raw_teams.get('red_team', []) if player.get('summonerId')]
                logger.info(f"🔄 Extracted from raw_teams_data - Blue: {blue_team}, Red: {red_team}")

        # Определяем, демо-режим или нет
        demo_mode = not blue_team and not red_team
        logger.info(f"🎮 Demo mode detected: {demo_mode}")

        # Если демо-режим и нет данных о командах, создаем демо-команды
        if demo_mode:
            logger.info("🔄 Creating demo teams...")
            all_players = safe_json_parse(room_data.get('players'), [])
            if not all_players:
                all_players = ['test_player', 'player2', 'player3', 'player4', 'player5']
                logger.info(f"🎭 Using default demo players: {all_players}")
            
            blue_team = all_players[:3]
            red_team = all_players[3:]
            logger.info(f"🎭 Demo blue_team: {blue_team}")
            logger.info(f"🎭 Demo red_team: {red_team}")

        # Определяем реальную команду пользователя
        try:
            user_actual_team = determine_player_team(summoner_id, blue_team, red_team, demo_mode)
            logger.info(f"✅ Determined team: {user_actual_team}")
        except HTTPException as e:
            logger.error(f"❌ Failed to determine team: {e.detail}")
            raise
        except Exception as e:
            logger.error(f"❌ Unexpected error in determine_player_team: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to determine player team: {str(e)}"
            )

        # Получаем Discord user ID с обработкой ошибок типа Redis
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
                            
                            # Fix the key by converting to hash
                            redis_manager.redis.delete(user_key)
                            redis_manager.redis.hset(user_key, "discord_user_id", str(discord_user_id))
                            logger.info("✅ Fixed Redis key type from string to hash")
                        except json.JSONDecodeError:
                            logger.error(f"❌ Failed to parse user data as JSON: {user_data}")
                except Exception as parse_error:
                    logger.error(f"❌ Failed to recover Discord ID: {parse_error}")
            else:
                raise e
        
        if not discord_user_id:
            logger.error(f"❌ Discord account not linked for user {summoner_id}")
            raise HTTPException(
                status_code=400,
                detail="Discord account not linked. Please link your Discord account first."
            )

        logger.info(f"🔗 Found Discord user ID: {discord_user_id}")

        # Выполняем назначение на команду
        logger.info(f"🔄 Assigning user to team: {user_actual_team}")
        success = await discord_service.assign_player_to_team(
            int(discord_user_id), match_id, user_actual_team
        )
        
        if success:
            logger.info(f"✅ Successfully auto-assigned user {discord_user_id} to {user_actual_team} in match {match_id}")
            
            # Получаем информацию о канале команды для возврата ссылки
            discord_channels = voice_service.get_voice_room_discord_channels(match_id)
            team_channel = None
            
            if user_actual_team == "Blue Team" and discord_channels.get('blue_team'):
                team_channel = discord_channels['blue_team']
            elif user_actual_team == "Red Team" and discord_channels.get('red_team'):
                team_channel = discord_channels['red_team']
            
            response_data = {
                "status": "success",
                "message": f"Automatically assigned to {user_actual_team}",
                "discord_user_id": discord_user_id,
                "team_name": user_actual_team,
                "match_id": match_id,
                "note": "You were automatically assigned to your actual team based on match data",
                "debug_info": {
                    "summoner_id": summoner_id,
                    "blue_team": blue_team,
                    "red_team": red_team,
                    "demo_mode": demo_mode
                }
            }
            
            # Добавляем информацию о канале если доступна
            if team_channel:
                response_data.update({
                    "discord_invite_url": team_channel.get('invite_url'),
                    "discord_channel_name": team_channel.get('channel_name'),
                    "secured": team_channel.get('secured', False)
                })
            
            logger.info(f"✅ Auto-assign completed successfully: {response_data}")
            return response_data
        else:
            logger.error("❌ Failed to assign user to team in Discord service")
            raise HTTPException(
                status_code=500,
                detail="Failed to assign to team. Make sure the match is active and channels are created."
            )
            
    except HTTPException:
        logger.error("❌ HTTPException in auto_assign_team")
        raise
    except Exception as e:
        logger.error(f"❌ Unexpected error in auto_assign_team: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to auto-assign team: {str(e)}"
        )


@router.get("/debug-team-assignment")
async def debug_team_assignment(
    match_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Debug endpoint to see exactly what's happening with team assignment."""
    try:
        summoner_id = current_user['sub']
        logger.info(f"🔍 DEBUG TEAM ASSIGNMENT for user {summoner_id}")
        
        # Get room data
        room_data = voice_service.redis.get_voice_room_by_match(match_id)
        if not room_data:
            return {"error": "Room not found"}
        
        logger.info(f"📊 RAW ROOM DATA: {room_data}")
        
        # Parse teams with detailed logging
        blue_team = safe_json_parse(room_data.get('blue_team'), [])
        red_team = safe_json_parse(room_data.get('red_team'), [])
        
        logger.info(f"🔵 PARSED BLUE TEAM: {blue_team} (type: {type(blue_team)})")
        logger.info(f"🔴 PARSED RED TEAM: {red_team} (type: {type(red_team)})")
        
        # Check raw teams data if available
        raw_teams_data = safe_json_parse(room_data.get('raw_teams_data'), {})
        logger.info(f"📋 RAW TEAMS DATA: {raw_teams_data}")
        
        # Try to determine team
        try:
            team = determine_player_team(summoner_id, blue_team, red_team, False)
            logger.info(f"🎯 DETERMINED TEAM: {team}")
        except Exception as e:
            logger.error(f"❌ Team determination failed: {e}")
            team = "Error"
        
        # Check LCU data directly
        lcu_teams = await lcu_service.lcu_connector.get_teams()
        logger.info(f"🎮 LCU TEAMS DATA: {lcu_teams}")
        
        return {
            "summoner_id": summoner_id,
            "room_blue_team": blue_team,
            "room_red_team": red_team,
            "determined_team": team,
            "raw_teams_data": raw_teams_data,
            "lcu_teams": lcu_teams,
            "room_data_keys": list(room_data.keys())
        }
        
    except Exception as e:
        logger.error(f"❌ Debug failed: {e}")
        return {"error": str(e)}


@router.post("/link-account")
async def link_discord_account(
    request: DiscordLinkRequest,
    current_user: dict = Depends(get_current_user)
):
    """Link Discord account to current LoL user."""
    try:
        summoner_id = current_user['sub']
        user_key = f"user:{summoner_id}"
        
        # Сохраняем Discord ID
        redis_manager.redis.hset(user_key, "discord_user_id", str(request.discord_user_id))
        
        # Обновляем время последнего обновления
        redis_manager.redis.hset(user_key, "discord_linked_at", datetime.now(timezone.utc).isoformat())
        
        logger.info(f"✅ Linked Discord account {request.discord_user_id} to summoner {summoner_id}")
        
        return {
            "status": "success",
            "message": "Discord account linked successfully",
            "discord_user_id": request.discord_user_id,
            "summoner_id": summoner_id
        }
        
    except Exception as e:
        logger.error(f"❌ Failed to link Discord account: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to link Discord account: {str(e)}"
        )


@router.get("/linked-account")
async def get_linked_discord_account(
    current_user: dict = Depends(get_current_user)
):
    """Get linked Discord account information."""
    try:
        user_key = f"user:{current_user['sub']}"
        discord_user_id = None
        
        try:
            # Try to get as hash first (correct way)
            discord_user_id = redis_manager.redis.hget(user_key, "discord_user_id")
        except redis.exceptions.ResponseError as e:
            if "WRONGTYPE" in str(e):
                logger.warning(f"⚠️ Redis key {user_key} has wrong type. Attempting recovery...")
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
        
        return {
            "summoner_id": current_user['sub'],
            "discord_user_id": discord_user_id,
            "linked": discord_user_id is not None
        }
    except Exception as e:
        logger.error(f"Failed to get linked account: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get linked account: {str(e)}"
        )


@router.delete("/unlink-account")
async def unlink_discord_account(
    current_user: dict = Depends(get_current_user)
):
    """Unlink Discord account from LoL summoner."""
    try:
        user_key = f"user:{current_user['sub']}"
        redis_manager.redis.delete(user_key)
        
        logger.info(f"Unlinked Discord account for summoner {current_user['sub']}")
        
        return {
            "status": "success",
            "message": "Discord account unlinked successfully"
        }
    except Exception as e:
        logger.error(f"Failed to unlink Discord account: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to unlink Discord account: {str(e)}"
        )


@router.get("/status")
async def get_discord_status():
    """Get Discord service status."""
    try:
        status = discord_service.get_status()
        return {
            "status": "success",
            "discord_service": status
        }
    except Exception as e:
        logger.error(f"Failed to get Discord status: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get Discord status: {str(e)}"
        )


@router.get("/user-info")
async def get_discord_user_info(
    discord_user_id: int,
    current_user: dict = Depends(get_current_user)
):
    """Get information about Discord user."""
    try:
        # This is a mock - in real implementation you'd fetch from Discord API
        # For now, we'll just return basic info
        user_exists = True  # Assume user exists for demo purposes
        
        return {
            "status": "success",
            "discord_user_id": discord_user_id,
            "user_exists": user_exists,
            "note": "This is a mock response. In production, would verify user exists in Discord guild."
        }
    except Exception as e:
        logger.error(f"Failed to get Discord user info: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get Discord user info: {str(e)}"
        )


@router.post("/admin/fix-redis-keys")
async def fix_redis_keys(current_user: dict = Depends(get_current_user)):
    """Admin endpoint to fix Redis key type issues."""
    try:
        redis_manager.fix_redis_key_types()
        return {
            "status": "success",
            "message": "Redis key type fix completed"
        }
    except Exception as e:
        logger.error(f"Failed to fix Redis keys: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fix Redis keys: {str(e)}"
        )


@router.post("/emergency-fix-teams")
async def emergency_fix_teams(
    match_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Emergency fix for team assignment - manually set teams based on LCU data."""
    try:
        logger.info(f"🚨 EMERGENCY FIX for match {match_id}")
        
        # Get current LCU team data
        teams_data = await lcu_service.lcu_connector.get_teams()
        if not teams_data:
            raise HTTPException(status_code=404, detail="No team data from LCU")
        
        logger.info(f"🎯 LCU Teams data: {teams_data}")
        
        # Extract player IDs
        blue_team_ids = [str(player.get('summonerId')) for player in teams_data.get('blue_team', []) if player.get('summonerId')]
        red_team_ids = [str(player.get('summonerId')) for player in teams_data.get('red_team', []) if player.get('summonerId')]
        
        logger.info(f"🔵 Blue team IDs: {blue_team_ids}")
        logger.info(f"🔴 Red team IDs: {red_team_ids}")
        
        # Get room data
        room_data = voice_service.redis.get_voice_room_by_match(match_id)
        if not room_data:
            raise HTTPException(status_code=404, detail="Room not found")
        
        # Update room data with correct teams
        room_id = room_data.get('room_id')
        if room_id:
            voice_service.redis.redis.hset(
                f"room:{room_id}",
                mapping={
                    'blue_team': json.dumps(blue_team_ids),
                    'red_team': json.dumps(red_team_ids)
                }
            )
            logger.info(f"✅ Updated room {room_id} with correct teams")
        
        return {
            "status": "success",
            "message": "Teams updated from LCU data",
            "blue_team": blue_team_ids,
            "red_team": red_team_ids,
            "match_id": match_id
        }
        
    except Exception as e:
        logger.error(f"❌ Emergency fix failed: {e}")
        raise HTTPException(status_code=500, detail=f"Emergency fix failed: {str(e)}")
