import hashlib
import hmac
import time

import pytest
from starlette.requests import Request

from tests.conftest import set_server_env, use_server_app


async def _make_request(method, path, query, body):
    async def receive():
        return {'type': 'http.request', 'body': body, 'more_body': False}

    scope = {
        'type': 'http',
        'http_version': '1.1',
        'method': method,
        'path': path,
        'query_string': query.encode('utf-8') if query else b'',
        'headers': [],
        'scheme': 'http',
        'server': ('testserver', 80),
        'client': ('testclient', 12345),
    }
    return Request(scope, receive)


@pytest.mark.asyncio
async def test_require_client_key_accepts_valid_signature():
    set_server_env()
    use_server_app()

    import importlib

    remote_key = importlib.import_module('app.utils.remote_key')

    shared_key = 'test_shared_key'
    body = b'{"hello":"world"}'
    ts = str(int(time.time()))
    path = '/api/client/match-start'
    query = 'x=1'
    full_path = f'{path}?{query}'

    body_hash = hashlib.sha256(body).hexdigest()
    message = f'{ts}\nPOST\n{full_path}\n{body_hash}'
    signature = hmac.new(shared_key.encode('utf-8'), message.encode(
        'utf-8'), hashlib.sha256).hexdigest()

    request = await _make_request('POST', path, query, body)

    await remote_key.require_client_key(
        request,
        x_rift_client_key=shared_key,
        x_rift_timestamp=ts,
        x_rift_signature=signature,
    )


@pytest.mark.asyncio
async def test_require_client_key_rejects_invalid_signature():
    set_server_env()
    use_server_app()

    import importlib
    from fastapi import HTTPException

    remote_key = importlib.import_module('app.utils.remote_key')

    shared_key = 'test_shared_key'
    body = b'{}'
    ts = str(int(time.time()))
    path = '/api/client/match-start'

    request = await _make_request('POST', path, '', body)

    with pytest.raises(HTTPException):
        await remote_key.require_client_key(
            request,
            x_rift_client_key=shared_key,
            x_rift_timestamp=ts,
            x_rift_signature='bad',
        )
