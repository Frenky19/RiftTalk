import asyncio
from fastapi import APIRouter, Depends, HTTPException, status
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
        
        # Создаем голосовую комнату
        result = await voice_service.create_voice_room(
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