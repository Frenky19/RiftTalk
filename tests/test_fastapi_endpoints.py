import hashlib
import hmac
import time
from contextlib import asynccontextmanager

from fastapi.testclient import TestClient

from tests.conftest import set_client_env, set_server_env, use_client_app, use_server_app


def _disable_lifespan(app):
    @asynccontextmanager
    async def _lifespan(_app):
        yield

    app.router.lifespan_context = _lifespan


def _make_signature(
    shared_key: str, method: str, path: str, query: str, body: bytes, ts: str
) -> str:
    full_path = f'{path}?{query}' if query else path
    body_hash = hashlib.sha256(body).hexdigest()
    message = f'{ts}\n{method}\n{full_path}\n{body_hash}'
    return hmac.new(shared_key.encode('utf-8'), message.encode(
        'utf-8'), hashlib.sha256).hexdigest()


def test_server_api_health():
    set_server_env()
    use_server_app()

    import importlib

    main = importlib.import_module('app.main')
    _disable_lifespan(main.app)

    client = TestClient(main.app)
    response = client.get('/api/health')

    assert response.status_code == 200
    data = response.json()
    assert data.get('ok') is True
    assert data.get('mode') == 'server'


def test_server_public_discord_login_url_signature():
    set_server_env()
    use_server_app()

    import importlib

    main = importlib.import_module('app.main')
    _disable_lifespan(main.app)

    client = TestClient(main.app)

    shared_key = 'test_shared_key'
    ts = str(int(time.time()))
    path = '/api/public/discord/login-url'
    query = 'summoner_id=1'
    body = b''
    signature = _make_signature(shared_key, 'GET', path, query, body, ts)

    response = client.get(
        path,
        params={'summoner_id': '1'},
        headers={
            'X-Rift-Client-Key': shared_key,
            'X-Rift-Timestamp': ts,
            'X-Rift-Signature': signature,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert 'url' in data
    assert data['url'].startswith('https://discord.com/api/oauth2/authorize')


def test_client_api_health():
    set_client_env()
    use_client_app()

    import importlib

    main = importlib.import_module('app.main')
    _disable_lifespan(main.app)

    client = TestClient(main.app)
    response = client.get('/api/health')

    assert response.status_code == 200
    data = response.json()
    assert data.get('ok') is True
    assert data.get('mode') == 'client'


def test_match_status_uses_cache(monkeypatch):
    set_client_env()
    use_client_app()

    import importlib

    main = importlib.import_module('app.main')
    security = importlib.import_module('app.utils.security')
    lcu_service_mod = importlib.import_module('app.services.lcu_service')
    remote_api_mod = importlib.import_module('app.services.remote_api')

    _disable_lifespan(main.app)

    async def _fake_user():
        return {'sub': '1', 'name': 'Tester'}

    main.app.dependency_overrides[security.get_current_user] = _fake_user

    class DummyLCU:
        def is_connected(self):
            return True

        async def get_game_flow_phase(self):
            return 'InProgress'

        async def get_current_session(self):
            return {'gameData': {'gameId': 42}}

        async def get_teams(self):
            return {
                'blue_team': [{'summonerId': '1'}],
                'red_team': [{'summonerId': '2'}],
            }

    lcu_service_mod.lcu_service.lcu_connector = DummyLCU()

    calls = {'count': 0}

    async def fake_match_start(payload):
        calls['count'] += 1
        return {
            'match_id': payload['match_id'],
            'team_name': 'Blue Team',
            'voice_channel': 'vc-1',
            'linked': True,
            'assigned': True,
        }

    monkeypatch.setattr(remote_api_mod.remote_api, 'match_start', fake_match_start)

    client = TestClient(main.app)

    response_1 = client.get('/api/discord/match-status/1')
    assert response_1.status_code == 200

    response_2 = client.get('/api/discord/match-status/1')
    assert response_2.status_code == 200

    assert calls['count'] == 1

    main.app.dependency_overrides.clear()
