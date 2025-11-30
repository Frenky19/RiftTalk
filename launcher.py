#!/usr/bin/env python3
"""
Launcher for LoL Voice Chat - Standalone Windows Application
Этот файл запускает Redis и наш веб-сервер автоматически
"""

import os
import sys
import subprocess
import time
import threading
import webbrowser


class LoLVoiceChatLauncher:
    def __init__(self):
        # Определяем где находится наша программа
        self.base_dir = self.get_base_dir()
        self.redis_process = None
        self.server_process = None
        self.is_running = True
        print("🎮 LoL Voice Chat Launcher")
        print("=" * 50)
        
    def get_base_dir(self):
        """Определяем папку где находится программа"""
        if getattr(sys, 'frozen', False):
            # Если программа собрана в exe
            return os.path.dirname(sys.executable)
        else:
            # Если запускаем как Python скрипт
            return os.path.dirname(os.path.abspath(__file__))
    
    def check_redis(self):
        """Проверяем запущен ли Redis"""
        try:
            import redis
            # Пробуем подключиться к Redis
            r = redis.Redis(host='localhost', port=6379, socket_connect_timeout=1)
            r.ping()
            return True
        except:
            return False
    
    def start_redis(self):
        """Запускаем Redis сервер"""
        redis_dir = os.path.join(self.base_dir, "redis")
        redis_exe = os.path.join(redis_dir, "redis-server.exe")
        redis_conf = os.path.join(redis_dir, "redis.conf")
        # Создаем папку redis если ее нет
        os.makedirs(redis_dir, exist_ok=True)
        # Проверяем есть ли Redis
        if not os.path.exists(redis_exe):
            print("❌ Redis не найден. Работаем в ограниченном режиме...")
            return None
        try:
            print("🔄 Запускаем Redis сервер...")
            # Запускаем Redis как отдельный процесс
            process = subprocess.Popen(
                [redis_exe, redis_conf],
                stdout=subprocess.DEVNULL,  # Не показываем вывод Redis
                stderr=subprocess.DEVNULL,
                cwd=redis_dir
            )
            # Ждем пока Redis запустится
            for i in range(10):
                if self.check_redis():
                    print("✅ Redis сервер запущен")
                    return process
                time.sleep(1)
            print("❌ Redis не смог запуститься")
            process.terminate()
            return None
        except Exception as e:
            print(f"❌ Ошибка запуска Redis: {e}")
            return None
    
    def start_server(self):
        """Запускаем наш веб-сервер"""
        try:
            print("🔄 Запускаем LoL Voice Chat сервер...")
            # Команда для запуска сервера
            cmd = [
                sys.executable, "-m", "uvicorn", 
                "app.main:app", 
                "--host", "0.0.0.0", 
                "--port", "8000"
            ]
            # Запускаем сервер
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            # Ждем пока сервер запустится
            for i in range(15):
                try:
                    import requests
                    # Пробуем подключиться к серверу
                    response = requests.get("http://localhost:8000/health", timeout=2)
                    if response.status_code == 200:
                        print("✅ Сервер запущен на http://localhost:8000")
                        return process
                except:
                    pass
                time.sleep(1)
            print("❌ Сервер не смог запуститься")
            return None
        except Exception as e:
            print(f"❌ Ошибка запуска сервера: {e}")
            return None
    
    def open_browser(self):
        """Открываем браузер после запуска сервера"""
        time.sleep(3)  # Ждем 3 секунды чтобы сервер точно запустился
        if self.is_running:
            print("🌐 Открываем браузер...")
            webbrowser.open("http://localhost:8000/link-discord")
    
    def run(self):
        """Главный метод запуска"""
        print("🎮 Запуск LoL Voice Chat...")
        try:
            # Запускаем Redis
            if not self.check_redis():
                self.redis_process = self.start_redis()
            else:
                print("✅ Redis уже запущен")
            # Запускаем сервер
            self.server_process = self.start_server()
            if not self.server_process:
                print("❌ Не удалось запустить сервер. Завершаем работу...")
                return
            # Открываем браузер в отдельном потоке
            browser_thread = threading.Thread(target=self.open_browser)
            browser_thread.daemon = True
            browser_thread.start()
            print("\n" + "=" * 50)
            print("🎉 LoL Voice Chat запущен!")
            print("📖 Откройте: http://localhost:8000/link-discord")
            print("🛑 Для остановки закройте это окно")
            print("=" * 50 + "\n")
            # Ждем пока пользователь не закроет окно
            while self.is_running:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n🛑 Остановка по команде пользователя...")
            self.cleanup()
        except Exception as e:
            print(f"❌ Критическая ошибка: {e}")
            self.cleanup()

    def cleanup(self):
        """Очистка при завершении"""
        print("🛑 Останавливаем LoL Voice Chat...")
        self.is_running = False
        # Останавливаем сервер
        if self.server_process:
            self.server_process.terminate()
        # Останавливаем Redis
        if self.redis_process:
            self.redis_process.terminate()
        print("✅ Все процессы остановлены")


if __name__ == "__main__":
    launcher = LoLVoiceChatLauncher()
    launcher.run()
