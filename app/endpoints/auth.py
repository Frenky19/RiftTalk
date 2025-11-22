from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from datetime import datetime, timezone, timedelta

from app.config import settings
from app.schemas import TokenResponse
from app.utils.security import create_access_token, verify_token
from app.database import redis_manager
from app.services.lcu_service import lcu_service

router = APIRouter(prefix="/auth", tags=["authentication"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")


@router.post("/token", response_model=TokenResponse)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends()
):
    """
    OAuth2-совместимый endpoint для получения JWT токена.
    Использует реальный summoner_id из LCU если доступно.
    """
    try:
        summoner_id = None
        summoner_name = form_data.username
        
        # Пробуем получить реальный summoner_id из LCU
        if lcu_service.lcu_connector.is_connected():
            current_summoner = await lcu_service.lcu_connector.get_current_summoner()
            if current_summoner:
                summoner_id = str(current_summoner.get('summonerId'))
                summoner_name = current_summoner.get('displayName') or current_summoner.get('gameName', summoner_name)
                print(f"✅ Using real summoner_id from LCU: {summoner_id}")
            else:
                print("⚠️ LCU connected but no summoner data - using provided username")
                summoner_id = form_data.username
        else:
            print("🔶 LCU not connected - using provided username as summoner_id")
            summoner_id = form_data.username
        
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
        
    except Exception as e:
        print(f"❌ Authentication error: {e}")
        # Fallback to basic authentication
        summoner_id = form_data.username
        summoner_name = form_data.username
        
        access_token_expires = timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
        access_token = create_access_token(
            data={"sub": summoner_id, "name": summoner_name},
            expires_delta=access_token_expires
        )
        
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


@router.post("/real-auth")
async def real_authentication():
    """
    Endpoint для аутентификации с реальным summoner_id из LCU.
    """
    try:
        if not lcu_service.lcu_connector.is_connected():
            raise HTTPException(
                status_code=503,
                detail="LCU not connected. Please launch League of Legends."
            )
            
        current_summoner = await lcu_service.lcu_connector.get_current_summoner()
        if not current_summoner:
            raise HTTPException(
                status_code=404,
                detail="No summoner data available"
            )
            
        summoner_id = str(current_summoner.get('summonerId'))
        summoner_name = current_summoner.get('displayName') or current_summoner.get('gameName', 'Unknown')
        
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
        
        return TokenResponse(
            access_token=access_token, 
            token_type="bearer",
            summoner_id=summoner_id,
            summoner_name=summoner_name
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Authentication failed: {str(e)}"
        )


@router.get("/auto-auth")
async def auto_authenticate():
    """
    Automatic authentication using LCU when available.
    Falls back to demo authentication if LCU not available.
    """
    try:
        # Try LCU authentication first
        if lcu_service.lcu_connector.is_connected():
            current_summoner = await lcu_service.lcu_connector.get_current_summoner()
            if current_summoner:
                summoner_id = str(current_summoner.get('summonerId'))
                summoner_name = current_summoner.get('displayName') or current_summoner.get('gameName', 'Unknown')
                
                access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
                access_token = create_access_token(
                    data={"sub": summoner_id, "name": summoner_name},
                    expires_delta=access_token_expires
                )
                
                # Save user info
                user_key = f"user:{summoner_id}"
                redis_manager.redis.hset(user_key, mapping={
                    "summoner_id": summoner_id,
                    "summoner_name": summoner_name,
                    "last_login": datetime.now(timezone.utc).isoformat(),
                    "auto_authenticated": "true"
                })
                redis_manager.redis.expire(user_key, 3600 * 24 * 7)
                
                return TokenResponse(
                    access_token=access_token,
                    token_type="bearer",
                    summoner_id=summoner_id,
                    summoner_name=summoner_name,
                    source="lcu_auto"
                )
        
        # Fallback to demo authentication
        demo_summoner_id = "demo_player_" + str(int(datetime.now(timezone.utc).timestamp()))
        demo_summoner_name = "DemoPlayer"
        
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": demo_summoner_id, "name": demo_summoner_name},
            expires_delta=access_token_expires
        )
        
        return TokenResponse(
            access_token=access_token,
            token_type="bearer", 
            summoner_id=demo_summoner_id,
            summoner_name=demo_summoner_name,
            source="demo_fallback"
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Auto-authentication failed: {str(e)}"
        )
