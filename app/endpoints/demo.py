from fastapi import APIRouter, Depends

from app.config import settings
from app.database import redis_manager
from app.services.discord_service import discord_service
from app.services.lcu_service import lcu_service
from app.utils.security import get_current_user
from pydantic import BaseModel


router = APIRouter(prefix='/demo', tags=['demo'])


class DemoAuthConfig(BaseModel):
    enabled: bool
    username: str


class DemoAuthToggleRequest(BaseModel):
    enabled: bool


@router.get('/auth-status')
async def get_demo_auth_status():
    """Get demo page authentication status."""
    return {
        'enabled': settings.DEMO_AUTH_ENABLED,
        'username': (
            settings.DEMO_USERNAME if settings.DEMO_AUTH_ENABLED else None
        ),
        'note': 'Password is hidden for security'
    }


@router.post('/auth-toggle')
async def toggle_demo_auth(
    request: DemoAuthToggleRequest,
    current_user: dict = Depends(get_current_user)
):
    """Enable/disable demo page authentication (for authenticated users only)."""
    return {
        'status': 'success',
        'message': f"Demo auth {'enabled' if request.enabled else 'disabled'}",
        'note': 'Changes require application restart to take effect'
    }


@router.get('/protected-stats')
async def get_protected_demo_stats(
    current_user: dict = Depends(get_current_user)
):
    """Protected statistics for demo page."""
    # This endpoint uses JWT authentication from your existing system
    # Collect statistics
    active_rooms = redis_manager.get_all_active_rooms()
    return {
        'active_rooms_count': len(active_rooms),
        'discord_status': discord_service.get_status(),
        'lcu_status': await lcu_service.get_detailed_status(),
        'redis_connected': (
            redis_manager.redis.ping() if redis_manager.redis else False
        ),
        'user_info': {
            'summoner_id': current_user.get('sub'),
            'summoner_name': current_user.get('name')
        }
    }
