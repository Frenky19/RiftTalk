"""
Security utilities for LoL Voice Chat - Simplified version for PyInstaller
"""

from datetime import datetime, timezone, timedelta
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from app.config import settings
import hashlib
import hmac
import secrets

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Упрощенная замена CryptContext для PyInstaller
class SimplePasswordHasher:
    """Упрощенный хешер паролей для демо-режима"""
    
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Упрощенная проверка пароля для демо-режима"""
        try:
            # Для демо-режима используем простую HMAC проверку
            expected_hash = SimplePasswordHasher.get_password_hash(plain_password)
            return hmac.compare_digest(expected_hash, hashed_password)
        except Exception:
            return False
    
    @staticmethod
    def get_password_hash(password: str) -> str:
        """Упрощенное хеширование пароля для демо-режима"""
        # Используем HMAC-SHA256 для демо-целей
        salt = "lol_voice_chat_demo_salt"  # В реальном приложении используйте уникальную соль
        return hmac.new(
            salt.encode('utf-8'),
            password.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()


# Используем упрощенный hasher
pwd_context = SimplePasswordHasher()


def create_access_token(data: dict, expires_delta: timedelta = None):
    """Create JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(
        to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )
    return encoded_jwt


def verify_token(token: str):
    """Verify JWT token"""
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
        return payload
    except JWTError:
        return None


async def get_current_user(token: str = Depends(oauth2_scheme)):
    """Get current user from token"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = verify_token(token)
    if not payload:
        raise credentials_exception
    return payload


# Сохраняем совместимость со старым кодом
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password (compatibility function)"""
    return pwd_context.verify_password(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Get password hash (compatibility function)"""
    return pwd_context.get_password_hash(password)