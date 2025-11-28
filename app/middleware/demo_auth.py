import base64
from fastapi import HTTPException, Request
from fastapi.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import Message
import logging

from app.config import settings

logger = logging.getLogger(__name__)


class DemoAuthMiddleware(BaseHTTPMiddleware):
    """Middleware для базовой аутентификации demo страницы"""
    
    async def dispatch(self, request: Request, call_next):
        # Проверяем, нужно ли защищать этот путь
        if not self._should_protect(request.url.path):
            return await call_next(request)
            
        # Проверяем аутентификацию
        auth_header = request.headers.get("Authorization")
        
        if not auth_header or not auth_header.startswith("Basic "):
            return self._get_unauthorized_response()
            
        try:
            credentials = base64.b64decode(auth_header[6:]).decode("utf-8")
            username, password = credentials.split(":", 1)
            
            if (username == settings.DEMO_USERNAME and password == settings.DEMO_PASSWORD):
                # Аутентификация успешна
                return await call_next(request)
                
        except Exception as e:
            logger.error(f"Auth error: {e}")
            
        return self._get_unauthorized_response()
    
    def _should_protect(self, path: str) -> bool:
        """Определяем, нужно ли защищать путь"""
        if not settings.DEMO_AUTH_ENABLED:
            return False
            
        # Публичные пути (без аутентификации)
        public_paths = [
            "/link-discord",
            "/static/link-discord.html",
            "/api/auth/auto-auth",  # Разрешаем авто-аутентификацию
            "/health"  # Health check тоже публичный
        ]
        
        # Проверяем, является ли путь публичным
        if any(path == public_path or path.startswith(public_path + '/') for public_path in public_paths):
            return False
            
        # Защищаем только demo-страницы
        protected_paths = ["/demo", "/static/demo.html"]
        return any(path.startswith(protected_path) for protected_path in protected_paths)
    
    def _get_unauthorized_response(self) -> Response:
        """Возвращает ответ с требованием аутентификации"""
        return Response(
            content="Authentication required",
            status_code=401,
            headers={"WWW-Authenticate": "Basic realm=\"Demo Page\""}
        )