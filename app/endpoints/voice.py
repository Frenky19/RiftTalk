from fastapi import APIRouter, Depends, HTTPException, status
from app.services.voice_service import voice_service
from app.schemas import MatchStartRequest, MatchEndRequest, VoiceRoomResponse
from app.utils.security import get_current_user
from app.config import settings

router = APIRouter(prefix="/voice", tags=["voice"])


@router.post("/start", response_model=VoiceRoomResponse)
async def start_voice_chat(
    request: MatchStartRequest,
    current_user: dict = Depends(get_current_user)
):
    """Create a new voice chat room for a match with Discord integration"""
    try:
        # В режиме разработки пропускаем проверку авторизации
        if not settings.DEBUG and current_user["sub"] not in request.players:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to create voice chat for this match"
            )
        # Подготавливаем данные команд для Discord
        team_data = {
            'blue_team': request.blue_team or [],
            'red_team': request.red_team or []
        }
        # Создаем голосовую комнату с Discord каналами
        voice_room = await voice_service.create_voice_room(
            request.match_id,
            request.players,
            team_data
        )
        return VoiceRoomResponse(
            room_id=voice_room.room_id,
            match_id=voice_room.match_id,
            players=voice_room.players,
            discord_channels=voice_room.discord_channels,
            created_at=voice_room.created_at.isoformat()
        )
    except Exception as e:
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
        return {"status": "success", "message": "Voice chat ended and Discord channels cleaned up"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to end voice chat: {str(e)}"
        )