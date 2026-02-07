import hashlib
import hmac
import json
import logging
import time
from typing import Any, Dict, Optional

import aiohttp

from app.config import settings
from app.constants import (
    REMOTE_API_HEALTH_TIMEOUT_SECONDS,
    REMOTE_API_TIMEOUT_SECONDS,
)

logger = logging.getLogger(__name__)


class RemoteAPIError(RuntimeError):
    pass


class RemoteAPI:
    """Async client for talking to the single remote RiftTalk server."""

    def __init__(self):
        self.base_url = (settings.REMOTE_SERVER_URL or '').rstrip('/')
        self.shared_key = settings.RIFT_SHARED_KEY or ''
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session and not self._session.closed:
            return self._session
        self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None

    def _headers(self) -> Dict[str, str]:
        return {
            'X-Rift-Client-Key': self.shared_key,
            'Content-Type': 'application/json',
        }

    def _signature_headers(
        self, method: str, path: str, body_bytes: bytes
    ) -> Dict[str, str]:
        ts = str(int(time.time()))
        body_hash = hashlib.sha256(body_bytes).hexdigest()
        message = f'{ts}\n{method.upper()}\n{path}\n{body_hash}'
        signature = hmac.new(
            self.shared_key.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return {
            'X-Rift-Timestamp': ts,
            'X-Rift-Signature': signature,
        }

    async def _request(
        self,
        method: str,
        path: str,
        json_body: Optional[dict] = None,
        timeout: int = REMOTE_API_TIMEOUT_SECONDS,
    ) -> Any:
        if not self.base_url:
            raise RemoteAPIError('REMOTE_SERVER_URL is not configured')
        url = f'{self.base_url}{path}'
        if json_body is None:
            body_bytes = b''
        else:
            body_bytes = json.dumps(
                json_body,
                separators=(',', ':'),
                ensure_ascii=False,
            ).encode('utf-8')
        headers = self._headers()
        headers.update(self._signature_headers(method, path, body_bytes))
        session = await self._get_session()
        try:
            async with session.request(
                method,
                url,
                data=body_bytes or None,
                headers=headers,
                timeout=timeout,
            ) as resp:
                text = await resp.text()
                try:
                    data = await resp.json(content_type=None)
                except Exception:
                    data = None
                if resp.status >= 400:
                    detail = None
                    if isinstance(data, dict):
                        detail = data.get('detail') or data.get('message')
                    raise RemoteAPIError(
                        f'Remote API {method} {path} failed: '
                        f'{resp.status} {detail or text}'
                    )
                return data if data is not None else text
        except aiohttp.ClientError as e:
            await self.close()
            raise RemoteAPIError(
                f'Remote API {method} {path} failed: '
                f'network error {type(e).__name__}: {e}'
            ) from e

    async def health(self) -> Any:
        return await self._request(
            'GET',
            '/api/health',
            timeout=REMOTE_API_HEALTH_TIMEOUT_SECONDS,
        )

    async def discord_login_url(self, summoner_id: str) -> Dict[str, Any]:
        return await self._request(
            'GET',
            f'/api/public/discord/login-url?summoner_id={summoner_id}',
        )

    async def linked_account(self, summoner_id: str) -> Dict[str, Any]:
        return await self._request(
            'GET',
            f'/api/public/discord/linked-account?summoner_id={summoner_id}',
        )

    async def user_server_status(self, discord_user_id: str) -> Dict[str, Any]:
        return await self._request(
            'GET',
            f'/api/public/discord/user-server-status/{discord_user_id}',
        )

    async def match_start(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request(
            'POST',
            '/api/client/match-start',
            json_body=payload,
        )

    async def match_end(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request(
            'POST',
            '/api/client/match-end',
            json_body=payload,
        )

    async def match_leave(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request(
            'POST',
            '/api/client/match-leave',
            json_body=payload,
        )

    async def voice_reconnect(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request(
            'POST',
            '/api/client/voice-reconnect',
            json_body=payload,
        )


remote_api = RemoteAPI()
