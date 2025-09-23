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
    """Create a new voice chat room for a match"""
    try:
        # В режиме разработки пропускаем проверку авторизации
        if settings.DEBUG:
            logger.info(f"DEBUG MODE: Skipping player authorization check")
        else:
            # Проверяем, что текущий пользователь есть в списке игроков
            if current_user["sub"] not in request.players:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Not authorized to create voice chat for this match"
                )
        
        # Создаем голосовую комнату
        voice_room = voice_service.create_voice_room(request.match_id, request.players)
        
        return VoiceRoomResponse(
            room_id=voice_room.room_id,
            match_id=voice_room.match_id,
            webrtc_config=voice_room.webrtc_config,
            players=voice_room.players
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create voice chat: {str(e)}"
        )
