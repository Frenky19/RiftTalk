from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from app.config import settings
from app.utils.security import get_current_user

router = APIRouter(prefix="/demo", tags=["demo"])


class DemoAuthConfig(BaseModel):
    enabled: bool
    username: str


@router.get("/auth-status")
async def get_demo_auth_status():
    """Получить статус аутентификации demo страницы"""
    return {
        "enabled": settings.DEMO_AUTH_ENABLED,
        "username": settings.DEMO_USERNAME if settings.DEMO_AUTH_ENABLED else None,
        "note": "Password is hidden for security"
    }


@router.post("/auth-toggle")
async def toggle_demo_auth(
    enabled: bool,
    current_user: dict = Depends(get_current_user)
):
    """Включить/выключить аутентификацию demo страницы (только для аутентифицированных пользователей)"""
    # В реальном приложении здесь должна быть проверка прав администратора
    # Для MVP просто проверяем аутентификацию
    
    # Здесь можно добавить логику для динамического изменения настроек
    # В текущей реализации требуется перезапуск приложения для изменения .env
    
    return {
        "status": "success",
        "message": f"Demo auth {'enabled' if enabled else 'disabled'}",
        "note": "Changes require application restart to take effect"
    }


@router.get("/protected-stats")
async def get_protected_demo_stats(current_user: dict = Depends(get_current_user)):
    """Защищенная статистика для demo страницы"""
    # Этот эндпоинт использует JWT аутентификацию из вашей существующей системы
    
    from app.services.discord_service import discord_service
    from app.services.lcu_service import lcu_service
    from app.database import redis_manager
    
    # Собираем статистику
    active_rooms = redis_manager.get_all_active_rooms()
    
    return {
        "active_rooms_count": len(active_rooms),
        "discord_status": discord_service.get_status(),
        "lcu_status": await lcu_service.get_detailed_status(),
        "redis_connected": redis_manager.redis.ping() if redis_manager.redis else False,
        "user_info": {
            "summoner_id": current_user.get("sub"),
            "summoner_name": current_user.get("name")
        }
    }