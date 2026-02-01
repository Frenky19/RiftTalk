import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER_ROOT = ROOT / 'server'
CLIENT_ROOT = ROOT / 'client'

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _reset_app_modules():
    for name in list(sys.modules.keys()):
        if name == 'app' or name.startswith('app.'):
            sys.modules.pop(name, None)


def use_server_app():
    _reset_app_modules()
    if str(CLIENT_ROOT) in sys.path:
        sys.path.remove(str(CLIENT_ROOT))
    if str(SERVER_ROOT) in sys.path:
        sys.path.remove(str(SERVER_ROOT))
    sys.path.insert(0, str(SERVER_ROOT))


def use_client_app():
    _reset_app_modules()
    if str(SERVER_ROOT) in sys.path:
        sys.path.remove(str(SERVER_ROOT))
    if str(CLIENT_ROOT) in sys.path:
        sys.path.remove(str(CLIENT_ROOT))
    sys.path.insert(0, str(CLIENT_ROOT))


def set_server_env():
    os.environ['APP_MODE'] = 'server'
    os.environ['RIFT_SHARED_KEY'] = 'test_shared_key'
    os.environ['JWT_SECRET_KEY'] = 'test-jwt-secret'
    os.environ['REDIS_URL'] = 'memory://'
    os.environ['DISCORD_BOT_TOKEN'] = 'test-token'
    os.environ['DISCORD_GUILD_ID'] = '1234567890'
    os.environ['DISCORD_OAUTH_CLIENT_ID'] = 'test-client-id'
    os.environ['DISCORD_OAUTH_CLIENT_SECRET'] = 'test-client-secret'
    os.environ['PUBLIC_BASE_URL'] = 'http://localhost:8001'


def set_client_env():
    os.environ['APP_MODE'] = 'client'
    os.environ['RIFT_SHARED_KEY'] = 'test_shared_key'
    os.environ['JWT_SECRET_KEY'] = 'test-jwt-secret'
    os.environ['REMOTE_SERVER_URL'] = 'http://localhost:8001'
    os.environ['REDIS_URL'] = 'memory://'
