#!/usr/bin/env python3
"""
Упрощенный launcher для LoL Voice Chat - Windows .exe (без Redis)
"""

import os
import sys
import threading
import webbrowser
import logging
import time

# Настройка базовых путей
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Добавляем пути для импорта
app_path = os.path.join(BASE_DIR, 'app')
if app_path not in sys.path:
    sys.path.insert(0, app_path)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(BASE_DIR, 'lol_voice_chat.log'), encoding='utf-8')
    ]
)

logger = logging.getLogger(__name__)

class SimpleLauncher:
    def __init__(self):
        self.is_running = True
        
    def setup_environment(self):
        """Настройка окружения"""
        logger.info("🔧 Настройка окружения...")
        
        # Логируем пути для отладки
        logger.info(f"📁 BASE_DIR: {BASE_DIR}")
        logger.info(f"📁 Current directory: {os.getcwd()}")
        
        static_path = os.path.join(BASE_DIR, "static")
        logger.info(f"📁 Static path: {static_path}")
        logger.info(f"📁 Static exists: {os.path.exists(static_path)}")
        
        if os.path.exists(static_path):
            files = os.listdir(static_path)
            logger.info(f"📄 Static files: {files}")
        
        # Устанавливаем переменные окружения для обхода Redis
        os.environ['REDIS_URL'] = 'memory://'  # Обходной путь для Redis
        os.environ['DEBUG'] = 'true'  # Включаем режим отладки
        
        # Устанавливаем текущую директорию на BASE_DIR
        os.chdir(BASE_DIR)
        logger.info(f"📁 Рабочая директория: {os.getcwd()}")
        
        # Создаем необходимые директории
        os.makedirs('logs', exist_ok=True)
        os.makedirs('data', exist_ok=True)
    
    def start_server(self):
        """Запуск сервера в отдельном потоке"""
        try:
            logger.info("🚀 Импорт и запуск сервера...")
            
            # Добавляем явный импорт dotenv до загрузки настроек
            try:
                from dotenv import load_dotenv
                load_dotenv(dotenv_path=os.path.join(BASE_DIR, '.env'))
                logger.info("✅ dotenv загружен")
            except Exception as e:
                logger.error(f"❌ Ошибка загрузки dotenv: {e}")
            
            # Импортируем и запускаем сервер
            import uvicorn
            
            # Загружаем наше приложение
            from app.main import app
            
            def run_server():
                try:
                    logger.info("🌐 Запуск Uvicorn сервера...")
                    uvicorn.run(
                        app,
                        host="0.0.0.0",
                        port=8000,
                        log_level="info",
                        access_log=False
                    )
                except Exception as e:
                    logger.error(f"❌ Ошибка сервера: {e}")
                    import traceback
                    logger.error(f"📋 Детали ошибки: {traceback.format_exc()}")
            
            server_thread = threading.Thread(target=run_server, daemon=True)
            server_thread.start()
            return server_thread
            
        except Exception as e:
            logger.error(f"❌ Ошибка запуска сервера: {e}")
            import traceback
            logger.error(f"📋 Детали ошибки: {traceback.format_exc()}")
            return None
    
    def check_server_ready(self, max_attempts=30):
        """Проверяем готовность сервера"""
        try:
            import requests
        except ImportError:
            logger.error("❌ Библиотека requests не установлена")
            return False
        
        for i in range(max_attempts):
            try:
                response = requests.get("http://localhost:8000/health", timeout=2)
                if response.status_code == 200:
                    logger.info("✅ Сервер запущен и готов")
                    return True
            except:
                if i % 5 == 0:  # Логируем каждые 5 попыток
                    logger.info(f"🔄 Ожидание сервера... ({i+1}/{max_attempts})")
            time.sleep(1)
        
        logger.error("❌ Сервер не запустился за отведенное время")
        return False
    
    def open_browser(self):
        """Открываем браузер"""
        time.sleep(3)
        if self.is_running:
            logger.info("🌐 Открываем браузер...")
            try:
                webbrowser.open("http://localhost:8000/link-discord")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось открыть браузер: {e}")
    
    def run(self):
        """Главный метод запуска"""
        print("🎮 LoL Voice Chat - Windows Launcher")
        print("=" * 50)
        
        try:
            # Настройка окружения
            self.setup_environment()
            
            # Запускаем сервер
            server_thread = self.start_server()
            if not server_thread:
                logger.error("❌ Не удалось запустить сервер")
                input("Нажмите Enter для выхода...")
                return
            
            # Проверяем готовность сервера
            if not self.check_server_ready():
                logger.error("❌ Сервер не запустился")
                input("Нажмите Enter для выхода...")
                return
            
            # Открываем браузер
            browser_thread = threading.Thread(target=self.open_browser, daemon=True)
            browser_thread.start()
            
            print("\n" + "=" * 50)
            print("🎉 LoL Voice Chat запущен!")
            print("📖 Откройте: http://localhost:8000/link-discord")
            print("📋 Логи: lol_voice_chat.log")
            print("🛑 Для остановки нажмите Ctrl+C")
            print("=" * 50 + "\n")
            
            # Ждем завершения
            try:
                while self.is_running:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\n🛑 Остановка по команде пользователя...")
                
        except Exception as e:
            logger.error(f"❌ Критическая ошибка: {e}")
            import traceback
            logger.error(f"📋 Детали ошибки: {traceback.format_exc()}")
            input("Нажмите Enter для выхода...")
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Очистка при завершении"""
        logger.info("🛑 Останавливаем LoL Voice Chat...")
        self.is_running = False


def main():
    """Точка входа"""
    launcher = SimpleLauncher()
    launcher.run()


if __name__ == "__main__":
    # Простой запуск для Windows
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 До свидания!")
    except Exception as e:
        print(f"❌ Фатальная ошибка: {e}")
        import traceback
        print(f"📋 Детали: {traceback.format_exc()}")
        input("Нажмите Enter для выхода...")