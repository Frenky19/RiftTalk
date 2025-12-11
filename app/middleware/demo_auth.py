import base64
import logging

from fastapi import Request
from fastapi.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings


logger = logging.getLogger(__name__)


class DemoAuthMiddleware(BaseHTTPMiddleware):
    """Middleware for basic authentication of demo pages."""

    async def dispatch(self, request: Request, call_next):
        # Check if this path should be protected
        if not self._should_protect(request.url.path):
            return await call_next(request)
        # Check authentication
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Basic '):
            return self._get_unauthorized_response()
        try:
            credentials = base64.b64decode(auth_header[6:]).decode('utf-8')
            username, password = credentials.split(':', 1)

            if (
                username == settings.DEMO_USERNAME and password == settings.DEMO_PASSWORD
            ):
                return await call_next(request)
        except Exception as e:
            logger.error(f'Auth error: {e}')
        return self._get_unauthorized_response()

    def _should_protect(self, path: str) -> bool:
        """Determine if path should be protected."""
        if not settings.DEMO_AUTH_ENABLED:
            return False
        # Public paths (no authentication required)
        public_paths = [
            '/link-discord',
            '/static/link-discord.html',
            '/api/auth/auto-auth',  # Allow auto-authentication
            '/health'  # Health check is also public
        ]
        # Check if path is public
        for public_path in public_paths:
            if path == public_path or path.startswith(public_path + '/'):
                return False
        # Protect only demo pages
        protected_paths = ['/demo', '/static/demo.html']
        return any(path.startswith(protected_path) for protected_path in protected_paths)

    def _get_unauthorized_response(self) -> Response:
        """Return response requiring authentication."""
        return Response(
            content='Authentication required',
            status_code=401,
            headers={'WWW-Authenticate': 'Basic realm="Demo Page"'}
        )
