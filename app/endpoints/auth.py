from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from datetime import datetime, timezone, timedelta

from app.config import settings
from app.schemas import TokenResponse
from app.utils.security import create_access_token, verify_token
from app.database import redis_manager

router = APIRouter(prefix="/auth", tags=["authentication"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")


@router.post("/token", response_model=TokenResponse)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends()
):
    """
    OAuth2-совместимый endpoint для получения JWT токена.
    В реальном приложении здесь должна быть проверка учетных данных.
    """
    # В демо-режиме просто создаем токен для любого пользователя
    # В продакшене нужно проверить учетные данные через Riot OAuth
    summoner_id = form_data.username
    summoner_name = form_data.username  # В реальности нужно получить из Riot API
    # Создаем токен доступа
    access_token_expires = timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    access_token = create_access_token(
        data={"sub": summoner_id, "name": summoner_name},
        expires_delta=access_token_expires
    )
    # Сохраняем информацию о пользователе в Redis
    user_key = f"user:{summoner_id}"
    redis_manager.redis.hset(user_key, mapping={
        "summoner_id": summoner_id,
        "summoner_name": summoner_name,
        "last_login": datetime.now(timezone.utc).isoformat()
    })
    redis_manager.redis.expire(user_key, 3600 * 24 * 7)
    return TokenResponse(access_token=access_token, token_type="bearer")


@router.post("/verify")
async def verify_access_token(token: str = Depends(oauth2_scheme)):
    """Проверка валидности JWT токена"""
    payload = verify_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return {"valid": True, "summoner_id": payload.get("sub")}


@router.post("/riot-auth")
async def riot_authentication(auth_data: dict):
    """
    Endpoint для аутентификации через Riot OAuth.
    В реальном приложении здесь должна быть интеграция с Riot OAuth2.
    """
    # Заглушка для демонстрации
    # В реальности нужно:
    # 1. Получить код авторизации от клиента
    # 2. Обменять код на access token через Riot API
    # 3. Получить информацию о пользователе
    # 4. Создать JWT токен для нашего приложения
    return {
        "status": "success", "message": "Riot authentication would be implemented here"
    }
