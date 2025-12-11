import logging
import os
import sys
import threading
import time
from pathlib import Path

if getattr(sys, 'frozen', False):
    try:
        from app.encrypted_env import decrypt_env  # type: ignore
        decrypt_env()
    except ImportError:
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass

if sys.platform == 'win32':
    try:
        if hasattr(sys, 'setdefaultencoding'):
            sys.setdefaultencoding('utf-8')
    except Exception:
        pass
    import codecs
    if sys.stdout:
        try:
            sys.stdout = codecs.getwriter('utf-8')(sys.stdout.detach())
        except Exception:
            pass
    if sys.stderr:
        try:
            sys.stderr = codecs.getwriter('utf-8')(sys.stderr.detach())
        except Exception:
            pass

if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent


class SafeFileHandler(logging.FileHandler):
    def __init__(self, filename, mode='a', encoding='utf-8', delay=False):
        super().__init__(filename, mode, encoding, delay)


log_file = BASE_DIR / 'lol_voice_chat.log'
handler = SafeFileHandler(log_file, encoding='utf-8')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[handler]
)

logger = logging.getLogger(__name__)

logging.getLogger('discord').setLevel(logging.WARNING)
logging.getLogger('uvicorn').setLevel(logging.WARNING)
logging.getLogger('websockets').setLevel(logging.WARNING)
logging.getLogger('asyncio').setLevel(logging.WARNING)


def setup_environment():
    logger.info('Setting up environment...')
    os.chdir(BASE_DIR)
    logger.info(f'Working directory: {BASE_DIR}')
    if getattr(sys, 'frozen', False):
        logger.info(
            'Running in frozen mode - using embedded environment variables'
        )
        if not os.environ.get('DISCORD_TOKEN'):
            logger.warning('DISCORD_TOKEN not found in environment variables')
    static_dir = BASE_DIR / 'static'
    if not static_dir.exists():
        if hasattr(sys, '_MEIPASS'):
            temp_static = Path(sys._MEIPASS) / 'static'
            if temp_static.exists():
                logger.info(f'Static found in temp dir: {temp_static}')
                import shutil
                shutil.copytree(temp_static, static_dir, dirs_exist_ok=True)
                logger.info(f'Static copied to: {static_dir}')
            else:
                logger.error('Static not found in BASE_DIR or temp dir')
                return False
        else:
            logger.error(f'Static folder not found in: {static_dir}')
            return False
    if not os.environ.get('REDIS_URL'):
        os.environ['REDIS_URL'] = 'memory://'
        logger.info('Set default REDIS_URL: memory://')
    if not os.environ.get('DEBUG'):
        os.environ['DEBUG'] = 'true'
        logger.info('Set default DEBUG: true')
    logger.info('Environment variables loaded')
    debug_vars = ['HOST', 'PORT', 'LOG_LEVEL', 'APP_ENV', 'DEBUG']
    for var in debug_vars:
        if var in os.environ:
            logger.info(f'{var} = {os.environ[var]}')
    return True


def start_fastapi_server():
    try:
        logger.info('Starting FastAPI server...')
        import uvicorn
        from app.main import app
        uvicorn.run(
            app,
            host='0.0.0.0',
            port=8000,
            log_level='warning',
            access_log=False,
            log_config=None
        )
    except Exception as e:
        logger.error(f'Server error: {e}')
        import traceback
        logger.error(f'Details: {traceback.format_exc()}')
        return False
    return True


def check_server_ready(timeout=30):
    import requests
    logger.info('Waiting for server to start...')
    for i in range(timeout):
        try:
            response = requests.get(
                'http://localhost:8000/health',
                timeout=2
            )
            if response.status_code == 200:
                logger.info('Server started')
                return True
        except Exception:
            if i % 5 == 0:
                logger.info(f'Waiting... ({i + 1}/{timeout})')
        time.sleep(1)
    logger.error('Server did not start')
    return False


def run_webview():
    try:
        import webview
        logger.info('Creating WebView window...')
        _ = webview.create_window(
            'LoL Voice Chat',
            'http://localhost:8000/link-discord',
            width=1200,
            height=800,
            resizable=True,
            fullscreen=False,
            min_size=(800, 600),
            confirm_close=False,
        )
        logger.info('Window created, starting WebView...')
        webview.start(debug=False)
        return True
    except ImportError:
        logger.error('Pywebview library not installed')
        return False
    except Exception as e:
        logger.error(f'WebView error: {e}')
        return False


def main():
    logger.info('=' * 50)
    logger.info('LoL Voice Chat Desktop (WebView version)')
    logger.info('=' * 50)
    if not setup_environment():
        logger.error('Failed to set up environment')
        return
    server_thread = threading.Thread(
        target=start_fastapi_server,
        daemon=True
    )
    server_thread.start()
    if not check_server_ready():
        logger.error('Server did not start')
        return
    if not run_webview():
        logger.info('Starting in browser as fallback...')
        import webbrowser
        webbrowser.open('http://localhost:8000/link-discord')
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info('Application terminated')
    logger.info('Application closed')


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.info('Application interrupted by user')
    except Exception as e:
        logger.error(f'Critical error: {e}')
        import traceback
        logger.error(traceback.format_exc())
