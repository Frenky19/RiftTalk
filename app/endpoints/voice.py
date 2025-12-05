import asyncio
import json
from fastapi import APIRouter, Depends, HTTPException, status
from app.services.lcu_service import lcu_service
from app.services.voice_service import voice_service
from app.services.discord_service import discord_service
from app.schemas import MatchStartRequest, MatchEndRequest, VoiceRoomResponse
from app.utils.security import get_current_user
from app.config import settings
import logging

router = APIRouter(prefix="/voice", tags=["voice"])

logger = logging.getLogger(__name__)


@router.post("/start")
async def start_voice_chat(
    request: MatchStartRequest,
    current_user: dict = Depends(get_current_user)
):
    """Create a new voice chat room for a match"""
    try:
        # Подготавливаем данные команд
        team_data = {
            'blue_team': request.blue_team or [],
            'red_team': request.red_team or []
        }
        
        # 🔥 ИСПРАВЛЕНИЕ: Используем create_or_get_voice_room вместо create_voice_room
        result = await voice_service.create_or_get_voice_room(
            request.match_id,
            request.players,
            team_data
        )
        
        if "error" in result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result["error"]
            )
            
        return result
        
    except Exception as e:
        logger.error(f"Voice chat creation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create voice chat: {str(e)}"
        )


@router.post("/end")
async def end_voice_chat(
    request: MatchEndRequest,
    current_user: dict = Depends(get_current_user)
):
    """End voice chat for a match and cleanup Discord channels"""
    try:
        success = await voice_service.close_voice_room(request.match_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No active voice chat found for this match"
            )
        return {
            "status": "success",
            "message": "Voice chat ended and Discord channels cleaned up",
            "match_id": request.match_id
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to end voice chat: {str(e)}"
        )


@router.post("/{match_id}/disconnect-members")
async def disconnect_members_from_match(
    match_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Disconnect all members from voice channels for a specific match."""
    try:
        # Получаем данные комнаты
        room_data = voice_service.redis.get_voice_room_by_match(match_id)
        if not room_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No active voice chat found for this match"
            )
        # Отключаем участников из каналов
        tasks = []
        discord_channels = voice_service.get_voice_room_discord_channels(match_id)
        
        if discord_channels:
            if discord_channels.get('blue_team') and not discord_channels['blue_team'].get('mock', True):
                channel_id = int(discord_channels['blue_team']['channel_id'])
                tasks.append(discord_service.disconnect_all_members(channel_id))
            if discord_channels.get('red_team') and not discord_channels['red_team'].get('mock', True):
                channel_id = int(discord_channels['red_team']['channel_id'])
                tasks.append(discord_service.disconnect_all_members(channel_id))
                
        if tasks:
            await asyncio.gather(*tasks)
        return {
            "status": "success",
            "message": f"All members disconnected from voice channels for match {match_id}",
            "match_id": match_id
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to disconnect members: {str(e)}"
        )


@router.delete("/admin/force-cleanup")
async def force_cleanup_all_matches(
    current_user: dict = Depends(get_current_user)
):
    """Force cleanup all voice channels and disconnect all members (admin only)."""
    try:
        # Получаем все активные комнаты
        active_rooms = voice_service.redis.get_all_active_rooms()
        # Отключаем всех участников со всех каналов
        cleanup_result = await discord_service.force_disconnect_all_matches()
        # Закрываем все комнаты в Redis
        closed_count = 0
        for room in active_rooms:
            try:
                success = await voice_service.close_voice_room(room['match_id'])
                if success:
                    closed_count += 1
            except Exception as e:
                logger.error(f"Failed to close room {room['match_id']}: {e}")
        return {
            "status": "success",
            "message": "Force cleanup completed",
            "disconnected_members": cleanup_result.get('disconnected_members', 0) if cleanup_result else 0,
            "channels_processed": cleanup_result.get('channels_processed', 0) if cleanup_result else 0,
            "rooms_closed": closed_count,
            "total_rooms": len(active_rooms)
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to force cleanup: {str(e)}"
        )


@router.get("/active-rooms")
async def get_active_voice_rooms(
    current_user: dict = Depends(get_current_user)
):
    """Get all active voice rooms."""
    try:
        active_rooms = voice_service.redis.get_all_active_rooms()
        return {
            "status": "success",
            "active_rooms": active_rooms,
            "count": len(active_rooms)
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get active rooms: {str(e)}"
        )


@router.post("/{match_id}/refresh-teams")
async def refresh_team_data(
    match_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Refresh team data for a voice room from LCU."""
    try:
        # Get current team data from LCU
        champ_select_data = await lcu_service.get_champ_select_data()
        if not champ_select_data:
            raise HTTPException(
                status_code=404,
                detail="No champ select data available from LCU"
            )
        
        # Get existing room
        room_data = voice_service.redis.get_voice_room_by_match(match_id)
        if not room_data:
            raise HTTPException(
                status_code=404,
                detail="Voice room not found"
            )
        
        # Update team data
        updated_team_data = {
            'blue_team': champ_select_data['teams'].get('blue_team', []),
            'red_team': champ_select_data['teams'].get('red_team', []),
            'raw_teams_data': champ_select_data.get('raw_teams_data')
        }
        
        # Update room in Redis
        room_id = room_data.get('room_id')
        if room_id:
            room_data['blue_team'] = json.dumps(updated_team_data['blue_team'])
            room_data['red_team'] = json.dumps(updated_team_data['red_team'])
            
            if updated_team_data.get('raw_teams_data'):
                room_data['raw_teams_data'] = json.dumps(updated_team_data['raw_teams_data'])
            
            success = voice_service.redis.redis.hset(
                f"room:{room_id}", 
                mapping={
                    'blue_team': room_data['blue_team'],
                    'red_team': room_data['red_team'],
                    'raw_teams_data': room_data.get('raw_teams_data', '')
                }
            )
            
            if success:
                return {
                    "status": "success",
                    "message": "Team data refreshed from LCU",
                    "match_id": match_id,
                    "blue_team": updated_team_data['blue_team'],
                    "red_team": updated_team_data['red_team']
                }
        
        raise HTTPException(
            status_code=500,
            detail="Failed to update team data"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to refresh team data: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to refresh team data: {str(e)}"
        )
        

@router.post("/admin/cleanup-expired")
async def cleanup_expired_rooms(current_user: dict = Depends(get_current_user)):
    """Cleanup all expired voice rooms (admin only)."""
    try:
        logger.info("🧹 Starting cleanup of expired rooms...")
        
        active_rooms = voice_service.redis.get_all_active_rooms()
        cleaned_count = 0
        error_count = 0
        
        logger.info(f"🔍 Found {len(active_rooms)} active rooms to check")
        
        for room in active_rooms:
            try:
                room_id = room.get('room_id')
                match_id = room.get('match_id')
                created_at = room.get('created_at')
                
                logger.info(f"🔄 Checking room {room_id} for match {match_id}")
                
                # Закрываем комнату (это вызовет cleanup Discord каналов)
                success = await voice_service.close_voice_room(match_id)
                
                if success:
                    cleaned_count += 1
                    logger.info(f"✅ Successfully cleaned up room for match {match_id}")
                else:
                    error_count += 1
                    logger.warning(f"⚠️ Failed to clean up room for match {match_id}")
                    
            except Exception as e:
                error_count += 1
                logger.error(f"❌ Error cleaning up room {room.get('room_id')}: {e}")
                continue
                
        return {
            "status": "success",
            "message": f"Cleanup completed: {cleaned_count} rooms cleaned, {error_count} errors",
            "cleaned_count": cleaned_count,
            "error_count": error_count,
            "total_rooms": len(active_rooms)
        }
        
    except Exception as e:
        logger.error(f"❌ Cleanup expired rooms failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Cleanup failed: {str(e)}"
        )


@router.post("/{match_id}/join-existing")
async def join_existing_voice_room(
    match_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Join an existing voice room for a match."""
    try:
        summoner_id = current_user['sub']
        
        # Проверяем, существует ли комната
        room_data = voice_service.redis.get_voice_room_by_match(match_id)
        if not room_data:
            raise HTTPException(
                status_code=404,
                detail="Voice room not found for this match"
            )
        
        # Определяем команду игрока
        blue_team = voice_service.safe_json_parse(room_data.get('blue_team'), [])
        red_team = voice_service.safe_json_parse(room_data.get('red_team'), [])
        
        team_name = None
        if summoner_id in blue_team:
            team_name = "Blue Team"
        elif summoner_id in red_team:
            team_name = "Red Team"
        
        if not team_name:
            raise HTTPException(
                status_code=400,
                detail="Player not found in any team for this match"
            )
        
        # Добавляем игрока в существующую комнату
        success = await voice_service.add_player_to_existing_room(summoner_id, match_id, team_name)
        
        if not success:
            raise HTTPException(
                status_code=500,
                detail="Failed to join existing voice room"
            )
        
        # Получаем Discord канал команды
        discord_channels = voice_service.get_voice_room_discord_channels(match_id)
        team_channel = None
        
        if team_name == "Blue Team" and discord_channels.get('blue_team'):
            team_channel = discord_channels['blue_team']
        elif team_name == "Red Team" and discord_channels.get('red_team'):
            team_channel = discord_channels['red_team']
        
        return {
            "status": "success",
            "message": f"Joined existing voice room for {team_name}",
            "match_id": match_id,
            "team_name": team_name,
            "room_id": room_data.get('room_id'),
            "discord_channel": team_channel
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to join existing room: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to join existing room: {str(e)}"
        )


@router.get("/{match_id}/status")
async def get_voice_room_status(
    match_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get status of a voice room including player count and channel info."""
    try:
        # Получаем данные комнаты
        room_data = voice_service.redis.get_voice_room_by_match(match_id)
        if not room_data:
            raise HTTPException(
                status_code=404,
                detail="Voice room not found"
            )
        
        # Получаем информацию о Discord каналах
        discord_channels = voice_service.get_voice_room_discord_channels(match_id)
        
        # Подсчитываем игроков
        players = voice_service.safe_json_parse(room_data.get('players'), [])
        blue_team = voice_service.safe_json_parse(room_data.get('blue_team'), [])
        red_team = voice_service.safe_json_parse(room_data.get('red_team'), [])
        
        return {
            "status": "success",
            "match_id": match_id,
            "room_id": room_data.get('room_id'),
            "total_players": len(players),
            "blue_team_count": len(blue_team),
            "red_team_count": len(red_team),
            "match_started": room_data.get('match_started') == 'true',
            "discord_channels": discord_channels,
            "is_active": room_data.get('is_active') == 'true',
            "created_at": room_data.get('created_at')
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get room status: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get room status: {str(e)}"
        )