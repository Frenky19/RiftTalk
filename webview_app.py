#!/usr/bin/env python3
"""
WebView приложение для LoL Voice Chat - Windows Desktop App
"""

import sys
import os
import threading
import time
import logging
from pathlib import Path

# ============ ИСПРАВЛЕНИЕ КОДИРОВКИ ДЛЯ WINDOWS ============
# Устанавливаем кодировку UTF-8 для всего приложения
if sys.platform == "win32":
    import locale
    # Пробуем установить UTF-8
    try:
        if hasattr(sys, "setdefaultencoding"):
            sys.setdefaultencoding("utf-8")
    except:
        pass
    
    # Исправляем кодировку для стандартных потоков
    import codecs
    if sys.stdout:
        try:
            sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())
        except:
            pass
    if sys.stderr:
        try:
            sys.stderr = codecs.getwriter("utf-8")(sys.stderr.detach())
        except:
            pass

# Настройка путей
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent

# Настройка логирования с исправлением кодировки
class SafeFileHandler(logging.FileHandler):
    """FileHandler с безопасной кодировкой UTF-8"""
    def __init__(self, filename, mode='a', encoding='utf-8', delay=False):
        super().__init__(filename, mode, encoding, delay)

# Используем безопасный обработчик
log_file = BASE_DIR / 'lol_voice_chat.log'
handler = SafeFileHandler(log_file, encoding='utf-8')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[handler]
)

logger = logging.getLogger(__name__)

# Также настраиваем логирование для других модулей
logging.getLogger('discord').setLevel(logging.WARNING)
logging.getLogger('uvicorn').setLevel(logging.WARNING)
logging.getLogger('websockets').setLevel(logging.WARNING)
logging.getLogger('asyncio').setLevel(logging.WARNING)

def setup_environment():
    """Настройка окружения"""
    logger.info("Настройка окружения...")
    
    # Устанавливаем рабочую директорию
    os.chdir(BASE_DIR)
    logger.info(f"Рабочая директория: {BASE_DIR}")
    
    # Проверяем наличие файлов
    env_file = BASE_DIR / '.env'
    if not env_file.exists():
        logger.error(f"Файл .env не найден в: {env_file}")
        return False
    logger.info(f"Найден .env файл: {env_file}")
    
    # Проверяем статические файлы
    static_dir = BASE_DIR / 'static'
    if not static_dir.exists():
        # Проверяем в temp директории PyInstaller
        if hasattr(sys, '_MEIPASS'):
            temp_static = Path(sys._MEIPASS) / 'static'
            if temp_static.exists():
                logger.info(f"Статика найдена в temp dir: {temp_static}")
                # Копируем статику в BASE_DIR
                import shutil
                shutil.copytree(temp_static, static_dir, dirs_exist_ok=True)
                logger.info(f"Статика скопирована в: {static_dir}")
            else:
                logger.error(f"Статика не найдена ни в BASE_DIR, ни в temp dir")
                return False
        else:
            logger.error(f"Папка static не найдена в: {static_dir}")
            return False
    
    # Настройка переменных окружения
    os.environ['REDIS_URL'] = 'memory://'
    os.environ['DEBUG'] = 'true'
    
    # Загружаем .env файл
    try:
        from dotenv import load_dotenv
        load_dotenv(env_file)
        logger.info("Файл .env загружен")
    except Exception as e:
        logger.warning(f"Не удалось загрузить .env: {e}")
    
    return True

def start_fastapi_server():
    """Запуск FastAPI сервера"""
    try:
        logger.info("Запуск FastAPI сервера...")
        
        # Используем тот же подход, что и в launcher.py
        import uvicorn
        
        # Импортируем приложение
        from app.main import app
        
        # Запускаем сервер с теми же параметрами
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=8000,
            log_level="warning",  # Изменяем на warning чтобы уменьшить логи
            access_log=False,
            log_config=None
        )
    except Exception as e:
        logger.error(f"Ошибка сервера: {e}")
        import traceback
        logger.error(f"Детали: {traceback.format_exc()}")
        return False
    return True

def check_server_ready(timeout=30):
    """Проверка готовности сервера"""
    import requests
    
    logger.info("Ожидание запуска сервера...")
    
    for i in range(timeout):
        try:
            response = requests.get("http://localhost:8000/health", timeout=2)
            if response.status_code == 200:
                logger.info("Сервер запущен")
                return True
        except:
            if i % 5 == 0:
                logger.info(f"Ожидание... ({i+1}/{timeout})")
        time.sleep(1)
    
    logger.error("Сервер не запустился")
    return False

def run_webview():
    """Запуск WebView"""
    try:
        import webview
        
        # Создаем окно
        logger.info("Создание WebView окна...")
        
        window = webview.create_window(
            'LoL Voice Chat',
            'http://localhost:8000/link-discord',
            width=1200,
            height=800,
            resizable=True,
            fullscreen=False,
            min_size=(800, 600),
            confirm_close=True
        )
        
        logger.info("Окно создано, запуск WebView...")
        
        # Запускаем WebView
        webview.start(debug=False)
        
        return True
        
    except ImportError:
        logger.error("Библиотека pywebview не установлена")
        return False
    except Exception as e:
        logger.error(f"Ошибка WebView: {e}")
        return False

def main():
    """Главная функция"""
    logger.info("=" * 50)
    logger.info("LoL Voice Chat Desktop (WebView версия)")
    logger.info("=" * 50)
    
    # Настройка окружения
    if not setup_environment():
        logger.error("Не удалось настроить окружение")
        return
    
    # Запускаем сервер в отдельном потоке
    server_thread = threading.Thread(target=start_fastapi_server, daemon=True)
    server_thread.start()
    
    # Ожидаем запуск сервера
    if not check_server_ready():
        logger.error("Сервер не запустился")
        return
    
    # Запускаем WebView
    if not run_webview():
        # Fallback: запускаем в браузере
        logger.info("Запуск в браузере как fallback...")
        import webbrowser
        webbrowser.open("http://localhost:8000/link-discord")
        
        # Держим приложение запущенным
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Приложение завершено")
    
    logger.info("Приложение закрыто")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Приложение прервано пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        import traceback
        logger.error(traceback.format_exc())