from fastapi import APIRouter, HTTPException, Depends
from app.services.lcu_service import lcu_service
from app.utils.security import get_current_user
from app.database import redis_manager

router = APIRouter(prefix="/lcu", tags=["lcu-integration"])


@router.get("/status")
async def lcu_connection_status(
    current_user: dict = Depends(get_current_user)
):
    """Проверка статуса подключения к LCU с детальной информацией."""
    try:
        detailed_status = await lcu_service.get_detailed_status()
        return {
            "status": "success",
            "lcu_service": detailed_status
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"LCU connection error: {str(e)}"
        )


@router.get("/current-game")
async def get_current_game_info(
    current_user: dict = Depends(get_current_user)
):
    """Получение детальной информации о текущей игре."""
    try:
        if not lcu_service.lcu_connector.is_connected():
            raise HTTPException(status_code=503, detail="LCU not connected")
        
        session = await lcu_service.lcu_connector.get_current_session()
        if not session:
            return {"status": "no_active_session"}
            
        game_phase = await lcu_service.lcu_connector.get_game_flow_phase()
        summoner = await lcu_service.lcu_connector.get_current_summoner()
        
        return {
            "status": "success",
            "game_phase": game_phase,
            "summoner": summoner,
            "session": session
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get game info: {str(e)}"
        )


@router.get("/current-summoner")
async def get_current_summoner_info(
    current_user: dict = Depends(get_current_user)
):
    """Получение информации о текущем призывателе."""
    try:
        if not lcu_service.lcu_connector.is_connected():
            raise HTTPException(status_code=503, detail="LCU not connected")
            
        summoner = await lcu_service.lcu_connector.get_current_summoner()
        if not summoner:
            return {"status": "no_summoner_info"}
            
        return {
            "status": "success",
            "summoner": summoner
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get summoner info: {str(e)}"
        )


@router.get("/teams")
async def get_current_teams(
    current_user: dict = Depends(get_current_user)
):
    """Получение информации о командах в текущей игре."""
    try:
        if not lcu_service.lcu_connector.is_connected():
            raise HTTPException(status_code=503, detail="LCU not connected")
            
        teams = await lcu_service.lcu_connector.get_teams()
        if not teams:
            return {"status": "no_team_data"}
            
        return {
            "status": "success",
            "teams": teams
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get teams: {str(e)}"
        )


@router.post("/auto-voice")
async def toggle_auto_voice(
    enabled: bool, current_user: dict = Depends(get_current_user)
):
    """Включение/выключение автоматического создания голосовых комнат."""
    try:
        # Сохраняем настройку пользователя
        user_key = f"user:{current_user['sub']}"
        redis_manager.redis.hset(
            user_key, "auto_voice", str(enabled).lower()
        )
        
        # Если включаем авто-войс и есть активная игра, создаем комнату
        if enabled and lcu_service.lcu_connector.is_connected():
            game_phase = await lcu_service.lcu_connector.get_game_flow_phase()
            if game_phase in ["ChampSelect", "InProgress"]:
                # Здесь можно автоматически создать комнату
                pass
                
        return {
            "status": "success", 
            "auto_voice": enabled,
            "message": f"Auto voice {'enabled' if enabled else 'disabled'}"
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to update settings: {str(e)}"
        )


@router.post("/force-reconnect")
async def force_lcu_reconnect(
    current_user: dict = Depends(get_current_user)
):
    """Принудительное переподключение к LCU."""
    try:
        await lcu_service.lcu_connector.disconnect()
        success = await lcu_service.lcu_connector.connect()
        
        return {
            "status": "success" if success else "failed",
            "reconnected": success,
            "message": "LCU reconnection attempted"
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to reconnect: {str(e)}"
        )
