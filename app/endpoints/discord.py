import logging
import json
import random
import redis  # Добавляем импорт
from fastapi import APIRouter, HTTPException, Depends
from app.services.discord_service import discord_service
from app.utils.security import get_current_user
from app.database import redis_manager
from app.schemas import DiscordLinkRequest, DiscordAssignRequest
from app.services.voice_service import voice_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/discord", tags=["discord-integration"])


def determine_player_team(summoner_id: str, blue_team: list, red_team: list, demo_mode: bool = False) -> str:
    """Determine which team the player belongs to."""
    logger.info(f"🔍 Determining team for summoner_id: {summoner_id}")
    logger.info(f"🔵 Blue team: {blue_team}")
    logger.info(f"🔴 Red team: {red_team}")
    logger.info(f"🎮 Demo mode: {demo_mode}")
    
    # Проверяем синюю команду
    if summoner_id in blue_team:
        logger.info(f"✅ Player {summoner_id} found in Blue Team")
        return "Blue Team"
    
    # Проверяем красную команду
    if summoner_id in red_team:
        logger.info(f"✅ Player {summoner_id} found in Red Team")
        return "Red Team"
    
    # Если игрок не найден в командах
    logger.warning(f"⚠️ Player {summoner_id} not found in any team")
    
    if demo_mode:
        # В демо-режиме назначаем случайно для тестирования
        team = random.choice(["Blue Team", "Red Team"])
        logger.info(f"🎲 Randomly assigned to {team} in demo mode")
        return team
    else:
        # В реальном режиме - ошибка
        raise HTTPException(
            status_code=400,
            detail=f"Player {summoner_id} not found in match teams"
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


@router.post("/link-account")
async def link_discord_account(
    request: DiscordLinkRequest,
    current_user: dict = Depends(get_current_user)
):
    """Link Discord account to LoL summoner."""
    try:
        logger.info(f"🔗 Linking Discord account {request.discord_user_id} to summoner {current_user['sub']}")
        
        # Save Discord user ID to Redis with proper type handling
        user_key = f"user:{current_user['sub']}"
        
        # Use HSET to ensure we're creating a hash
        redis_manager.redis.hset(user_key, "discord_user_id", str(request.discord_user_id))
        redis_manager.redis.expire(user_key, 604800)  # 7 days
        
        logger.info(f"✅ Successfully linked Discord account {request.discord_user_id} to summoner {current_user['sub']}")
        
        return {
            "status": "success",
            "message": "Discord account linked successfully",
            "discord_user_id": request.discord_user_id,
            "summoner_id": current_user['sub']
        }
    except Exception as e:
        logger.error(f"❌ Failed to link Discord account: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to link Discord account: {str(e)}"
        )


@router.post("/assign-to-team")
async def assign_to_team(
    request: DiscordAssignRequest,
    current_user: dict = Depends(get_current_user)
):
    """Assign Discord user to team role."""
    try:
        logger.info(f"🎯 Manual assign: user {current_user['sub']} to {request.team_name} in match {request.match_id}")
        
        # Get Discord user ID from Redis with proper error handling
        user_key = f"user:{current_user['sub']}"
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
            logger.error(f"❌ Discord account not linked for user {current_user['sub']}")
            raise HTTPException(
                status_code=400,
                detail="Discord account not linked. Please link your Discord account first using /api/discord/link-account"
            )

        # Validate team name
        if request.team_name not in ["Blue Team", "Red Team"]:
            logger.error(f"❌ Invalid team name: {request.team_name}")
            raise HTTPException(
                status_code=400,
                detail="Team name must be either 'Blue Team' or 'Red Team'"
            )

        logger.info(f"🔗 Assigning Discord user {discord_user_id} to {request.team_name}")
        
        # Assign to team role
        success = await discord_service.assign_player_to_team(
            int(discord_user_id),
            request.match_id,
            request.team_name
        )
        
        if success:
            logger.info(f"✅ Successfully assigned user {discord_user_id} to {request.team_name} in match {request.match_id}")
            
            # Получаем информацию о канале команды для возврата ссылки
            discord_channels = voice_service.get_voice_room_discord_channels(request.match_id)
            team_channel = None
            
            if request.team_name == "Blue Team" and discord_channels.get('blue_team'):
                team_channel = discord_channels['blue_team']
            elif request.team_name == "Red Team" and discord_channels.get('red_team'):
                team_channel = discord_channels['red_team']
            
            response_data = {
                "status": "success",
                "message": f"Assigned to {request.team_name} in match {request.match_id}",
                "discord_user_id": discord_user_id,
                "team_name": request.team_name,
                "match_id": request.match_id
            }
            
            # Добавляем информацию о канале если доступна
            if team_channel:
                response_data.update({
                    "discord_invite_url": team_channel.get('invite_url'),
                    "discord_channel_name": team_channel.get('channel_name')
                })
            
            return response_data
        else:
            logger.error(f"❌ Failed to assign user {discord_user_id} to team role")
            raise HTTPException(
                status_code=500,
                detail="Failed to assign to team role. Make sure the match is active and channels are created."
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to assign to team: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to assign to team: {str(e)}"
        )


@router.post("/auto-assign-team")
async def auto_assign_team(
    match_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Automatically assign user to their actual team based on match data."""
    try:
        logger.info(f"🎯 Auto-assign: user {current_user['sub']} for match {match_id}")
        
        # Получаем информацию о матче
        room_data = voice_service.redis.get_voice_room_by_match(match_id)
        if not room_data:
            logger.error(f"❌ Match not found: {match_id}")
            raise HTTPException(status_code=404, detail="Match not found")

        logger.info(f"📊 Room data keys: {list(room_data.keys())}")
        logger.info(f"📊 Room data: {room_data}")

        # Получаем summoner_id текущего пользователя
        summoner_id = current_user['sub']
        logger.info(f"👤 Current summoner_id: {summoner_id}")

        # Получаем данные о командах с безопасным парсингом
        blue_team = safe_json_parse(room_data.get('blue_team'), [])
        red_team = safe_json_parse(room_data.get('red_team'), [])
        
        logger.info(f"🔵 Parsed blue_team: {blue_team}")
        logger.info(f"🔴 Parsed red_team: {red_team}")

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
                "note": "You were automatically assigned to your actual team based on match data"
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