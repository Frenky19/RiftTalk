"""Desktop launcher for RiftTalk (FastAPI + pywebview).

This script:
- Loads environment variables (supports frozen builds).
- Ensures required static assets are available next to the executable.
- Starts the FastAPI backend in a background thread.
- Opens the UI in an embedded pywebview window (with a browser fallback).

Note: The window icon for pywebview is set only if the installed pywebview
version supports the `icon` parameter.
"""

import asyncio
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


class WebViewAPI:
    """Exposes small helpers to JS inside pywebview."""

    def open_browser(self, url: str) -> bool:
        try:
            import webbrowser
            webbrowser.open(url)
            return True
        except Exception:
            return False


class SafeFileHandler(logging.FileHandler):
    """A FileHandler that defaults to UTF-8 (helps on Windows/frozen builds)."""

    def __init__(self, filename, mode='a', encoding='utf-8', delay=False):
        super().__init__(filename, mode, encoding, delay)


def _configure_logging() -> logging.Logger:
    """Configure app logging.

    By default (release/frozen build) we do NOT write a log file next to the exe,
    because it clutters the user's folder.

    Enable file logging explicitly by setting env var:
        LOLVC_LOG_TO_FILE=1

    In dev mode (non-frozen) file logging is enabled by default.
    """
    is_frozen = bool(getattr(sys, 'frozen', False))
    want_file = (
        os.getenv('LOLVC_LOG_TO_FILE', '').strip().lower()
        in ('1', 'true', 'yes', 'on')
    )
    enable_file_logging = want_file or (not is_frozen)
    if enable_file_logging:
        log_file = BASE_DIR / 'lol_voice_chat.log'
        handler = SafeFileHandler(log_file, encoding='utf-8')
        handlers = [handler]
    else:
        # No file, no console (windowed) => quiet by default
        handlers = []
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=handlers if handlers else None,
    )
    return logging.getLogger(__name__)


logger = _configure_logging()


def _get_server_config():
    """Return (bind_host, port, ui_base_url).
    bind_host may be 0.0.0.0, but UI should use a loopback host."""
    try:
        from app.config import settings
        bind_host = getattr(settings, 'SERVER_HOST', '127.0.0.1') or '127.0.0.1'
        port = int(getattr(settings, 'SERVER_PORT', 8000) or 8000)
    except Exception:
        bind_host, port = '127.0.0.1', 8000
    ui_host = '127.0.0.1' if bind_host in ('0.0.0.0', '::') else bind_host
    base_url = f'http://{ui_host}:{port}'
    return bind_host, port, base_url


logging.getLogger('discord').setLevel(logging.WARNING)
logging.getLogger('uvicorn').setLevel(logging.WARNING)
logging.getLogger('websockets').setLevel(logging.WARNING)
logging.getLogger('asyncio').setLevel(logging.WARNING)


def setup_environment():
    """Prepare runtime environment for the desktop app.

        Responsibilities:
            - Switch CWD to BASE_DIR.
            - Ensure `static/` exists next to the executable.
            - Set safe defaults for a few environment variables.

        Returns:
            bool: True if the environment is ready, otherwise False."""
    logger.info('Setting up environment...')
    os.chdir(BASE_DIR)
    logger.info(f'Working directory: {BASE_DIR}')
    if getattr(sys, 'frozen', False):
        logger.info(
            'Running in frozen mode - using embedded environment variables'
        )
        if not os.environ.get('DISCORD_TOKEN'):
            logger.warning('DISCORD_TOKEN not found in environment variables')
    # IMPORTANT:
    # Do NOT copy embedded `static/` next to the executable.
    # In PyInstaller onefile mode, bundled resources are already extracted to
    # a temporary directory (sys._MEIPASS). We point the backend to that path.
    static_dir = BASE_DIR / 'static'
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        temp_static = Path(sys._MEIPASS) / 'static'
        if temp_static.exists():
            os.environ['RIFT_STATIC_DIR'] = str(temp_static)
            logger.info(f'Using embedded static from: {temp_static}')
        elif static_dir.exists():
            os.environ['RIFT_STATIC_DIR'] = str(static_dir)
            logger.info(f'Using static next to exe (fallback): {static_dir}')
        else:
            logger.error('Static not found in embedded temp dir or next to exe')
            return False
    else:
        # Dev mode
        if static_dir.exists():
            nested_static = static_dir / 'static'
            if (nested_static / 'link-discord.html').exists():
                os.environ['RIFT_STATIC_DIR'] = str(nested_static)
            else:
                os.environ['RIFT_STATIC_DIR'] = str(static_dir)
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
    """Start the FastAPI backend using Uvicorn.

        This runs in a background thread (daemon=True) so the UI can be launched.

        Returns:
            bool: True on clean shutdown, False if an exception occurred."""
    try:
        logger.info('Starting FastAPI server...')
        import uvicorn

        from app.main import app
        bind_host, port, _ = _get_server_config()
        uvicorn.run(
            app,
            host=bind_host,
            port=port,
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


def check_server_ready(timeout=60):
    """Poll the backend health endpoint until it responds or a timeout is reached.

        Args:
            timeout (int): Maximum number of seconds to wait.

        Returns:
            bool: True if the server answered with HTTP 200, otherwise False."""
    from urllib.error import HTTPError, URLError
    from urllib.request import ProxyHandler, Request, build_opener

    _, _, base_url = _get_server_config()
    health_url = f'{base_url}/api/health'
    logger.info(f'Waiting for server to start at: {health_url}')
    # Force direct localhost checks: never use system HTTP(S) proxy here.
    opener = build_opener(ProxyHandler({}))
    last_error = None
    for i in range(timeout):
        try:
            req = Request(health_url, method='GET')
            with opener.open(req, timeout=2) as response:
                status = response.getcode()
                body_preview = (
                    response.read(200).decode('utf-8', errors='ignore').strip()
                )
            if status == 200:
                logger.info('Server started')
                return True
            body_preview = body_preview.replace('\n', ' ')
            if len(body_preview) > 160:
                body_preview = body_preview[:160] + '...'
            last_error = f'HTTP {status} body={body_preview}'
            if i % 10 == 0:
                logger.warning(
                    f'Healthcheck non-200 ({i + 1}/{timeout}): {last_error}'
                )
        except HTTPError as e:
            body_preview = ''
            try:
                body_preview = (
                    e.read(200).decode('utf-8', errors='ignore').strip()
                )
            except Exception:
                body_preview = ''
            body_preview = body_preview.replace('\n', ' ')
            if len(body_preview) > 160:
                body_preview = body_preview[:160] + '...'
            last_error = f'HTTP {e.code} body={body_preview}'
            if i % 10 == 0:
                logger.warning(
                    f'Healthcheck non-200 ({i + 1}/{timeout}): {last_error}'
                )
        except URLError as e:
            last_error = f'request failed: {e.reason}'
            if i % 5 == 0:
                logger.info(f'Waiting... ({i + 1}/{timeout})')
        except Exception as e:
            last_error = f'request failed: {e}'
            if i % 5 == 0:
                logger.info(f'Waiting... ({i + 1}/{timeout})')
        time.sleep(1)
    logger.error(f'Server did not start (last_error={last_error})')
    return False


def run_webview():
    """Launch the UI inside a pywebview window.

        - Builds the URL from the running backend config.
        - Tries to set a custom icon when supported by the installed pywebview version.
        - Returns False on failure, which triggers a browser fallback in `main()`.

        Returns:
            bool: True if the window was started successfully, otherwise False."""
    try:
        import webview
        logger.info('Creating WebView window...')
        _ = webview.create_window(
            'RiftTalk',
            f'{_get_server_config()[2]}/link-discord',
            js_api=WebViewAPI(),
            width=1400,
            height=1350,
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
    """Application entrypoint.

    Flow:
        1) Prepare environment and static assets.
        2) Start the FastAPI server in a daemon thread.
        3) Wait for backend readiness.
        4) Open the UI in pywebview (or in a browser as fallback)."""

    logger.info('=' * 50)
    logger.info('RiftTalk (WebView version)')
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
        webbrowser.open(f'{_get_server_config()[2]}/link-discord')
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info('Application terminated')
    else:
        try:
            from app.services.shutdown_cleanup import notify_match_leave_on_shutdown
            asyncio.run(
                notify_match_leave_on_shutdown(
                    allow_lcu=False,
                )
            )
        except Exception as e:
            logger.warning(f'Shutdown match-leave failed: {e}')
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
