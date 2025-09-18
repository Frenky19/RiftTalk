from fastapi import APIRouter, HTTPException, Depends
from app.services.lcu_service import lcu_service
from app.utils.security import get_current_user

router = APIRouter(prefix="/lcu", tags=["lcu-integration"])

@router.get("/status")
async def lcu_connection_status(current_user: dict = Depends(get_current_user)):
    """Проверка статуса подключения к LCU"""
    try:
        is_connected = lcu_service.lcu_connector.is_connected()
        return {
            "connected": is_connected,
            "port": lcu_service.lcu_connector.lockfile_data.get("port") if is_connected else None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LCU connection error: {str(e)}")

@router.get("/current-game")
async def get_current_game_info(current_user: dict = Depends(get_current_user)):
    """Получение информации о текущей игре"""
    try:
        if not lcu_service.lcu_connector.is_connected():
            raise HTTPException(status_code=503, detail="LCU not connected")
        
        game_info = await lcu_service.get_current_match()
        if not game_info:
            return {"status": "no_active_game"}
        
        return game_info
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get game info: {str(e)}")

@router.post("/auto-voice")
async def toggle_auto_voice(enabled: bool, current_user: dict = Depends(get_current_user)):
    """Включение/выключение автоматического создания голосовых комнат"""
    try:
        # Сохраняем настройку пользователя
        user_key = f"user:{current_user['sub']}"
        redis_manager.redis.hset(user_key, "auto_voice", str(enabled).lower())
        
        return {"status": "success", "auto_voice": enabled}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update settings: {str(e)}")