"""
Build script for LoL Voice Chat - Обходной путь
"""

import os
import sys
import shutil
import subprocess
import tempfile
import time


def force_remove(path):
    """Принудительное удаление с использованием разных методов"""
    if not os.path.exists(path):
        return True
    # Метод 1: Попробовать переименовать и затем удалить
    try:
        temp_name = path + "_old_" + str(int(time.time()))
        os.rename(path, temp_name)
        shutil.rmtree(temp_name, ignore_errors=True)
        print(f"✅ Удалено через переименование: {path}")
        return True
    except:
        pass
    # Метод 2: Использовать команду Windows
    try:
        if os.name == 'nt':
            subprocess.run(['cmd', '/c', 'rmdir', '/s', '/q', path], capture_output=True, timeout=10)
        else:
            subprocess.run(['rm', '-rf', path], capture_output=True, timeout=10)
        print(f"✅ Удалено через системную команду: {path}")
        return True
    except:
        pass
    
    # Метод 3: Игнорировать ошибку и продолжить
    print(f"⚠️ Не удалось удалить {path}, продолжаем без очистки")
    return False


def build_with_workaround():
    """Сборка с обходом проблем с правами доступа"""
    print("🔨 Сборка LoL Voice Chat (обходной путь)...")
    # Пытаемся очистить папки, но не блокируемся на ошибках
    print("🗑️ Пытаемся очистить папки сборки...")
    force_remove("dist")
    force_remove("build")
    # Создаем временную папку для сборки
    temp_build_dir = tempfile.mkdtemp(prefix="lol_build_")
    print(f"📁 Временная папка сборки: {temp_build_dir}")
    try:
        # Собираем в временную папку
        cmd = [
            "pyinstaller",
            "--name=LoLVoiceChat",
            "--onefile",
            "--console",
            f"--distpath={temp_build_dir}/dist",
            f"--workpath={temp_build_dir}/build",
            "--specpath=.",
            "--add-data=app;app",
            "--add-data=static;static", 
            "--add-data=redis;redis",
            "--add-data=.env;.",
            # Основные hidden-imports
            "--hidden-import=uvicorn.lifespan.on",
            "--hidden-import=uvicorn.lifespan.off",
            "--hidden-import=app.main",
            "--hidden-import=app.config",
            "--hidden-import=app.database",
            "--hidden-import=app.models",
            "--hidden-import=app.schemas",
            "--hidden-import=app.utils.exceptions", 
            "--hidden-import=app.utils.security",
            "--hidden-import=app.utils.logger",
            "--hidden-import=app.utils.lcu_connector",
            "--hidden-import=app.services.lcu_service",
            "--hidden-import=app.services.discord_service",
            "--hidden-import=app.services.voice_service",
            "--hidden-import=app.services.cleanup_service",
            "--hidden-import=app.endpoints.voice",
            "--hidden-import=app.endpoints.auth",
            "--hidden-import=app.endpoints.lcu",
            "--hidden-import=app.endpoints.discord",
            "--hidden-import=app.endpoints.demo",
            "--hidden-import=app.middleware.demo_auth",
            "launcher.py"
        ]
        print("🚀 Запускаем PyInstaller...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        print("=== STDOUT ===")
        print(result.stdout)
        if result.stderr:
            print("=== STDERR ===")
            print(result.stderr)
        # Проверяем результат в временной папке
        temp_exe = os.path.join(temp_build_dir, "dist", "LoLVoiceChat.exe")
        if os.path.exists(temp_exe):
            print(f"✅ Исполняемый файл создан: {temp_exe}")
            # Создаем нашу папку dist если ее нет
            os.makedirs("dist", exist_ok=True)
            # Копируем исполняемый файл из временной папки
            final_exe = "dist/LoLVoiceChat.exe"
            shutil.copy2(temp_exe, final_exe)
            print(f"✅ Файл скопирован в: {final_exe}")
            # Создаем пакет
            create_package(final_exe)
            return True
        else:
            print("❌ Исполняемый файл не создан в временной папке")
            # Покажем что есть в временной папке
            if os.path.exists(temp_build_dir):
                print("Содержимое временной папки:")
                for root, dirs, files in os.walk(temp_build_dir):
                    level = root.replace(temp_build_dir, "").count(os.sep)
                    indent = " " * 2 * level
                    print(f"{indent}{os.path.basename(root)}/")
                    for file in files:
                        print(f"{indent}  {file}")
            return False
    except subprocess.TimeoutExpired:
        print("❌ Сборка заняла слишком много времени")
        return False
    except Exception as e:
        print(f"❌ Неожиданная ошибка: {e}")
        return False
    finally:
        # Очищаем временную папку
        try:
            shutil.rmtree(temp_build_dir, ignore_errors=True)
            print(f"✅ Временная папка очищена: {temp_build_dir}")
        except:
            print(f"⚠️ Не удалось очистить временную папку: {temp_build_dir}")


def create_package(exe_path):
    """Создаем дистрибутивный пакет"""
    print("📦 Создаем пакет...")
    package_dir = "dist/LoLVoiceChat_Package"
    # Создаем папку для пакета
    os.makedirs(package_dir, exist_ok=True)
    # Копируем исполняемый файл
    shutil.copy2(exe_path, os.path.join(package_dir, "LoLVoiceChat.exe"))
    print("✅ Исполняемый файл скопирован в пакет")
    # Копируем файлы Redis
    if os.path.exists("redis"):
        shutil.copytree("redis", os.path.join(package_dir, "redis"), dirs_exist_ok=True)
        print("✅ Redis скопирован")
    # Копируем конфигурационные файлы
    if os.path.exists(".env"):
        shutil.copy2(".env", package_dir)
        print("✅ .env скопирован")
    # Создаем README файл
    readme_content = """# LoL Voice Chat

Автоматический голосовой чат для команд в League of Legends.

## Установка

1. Распакуйте этот ZIP файл в любую папку
2. Запустите `LoLVoiceChat.exe`
3. Приложение автоматически:
   - Запустит сервер голосового чата
   - Откроет браузер со страницей настройки
   - Будет работать в фоновом режиме

## Использование

1. **Привяжите Discord аккаунт**: Следуйте инструкциям в браузере чтобы привязать ваш Discord аккаунт
2. **Играйте в League of Legends**: Приложение автоматически обнаружит ваши игры
3. **Голосовой чат**: Вы будете автоматически помещены в голосовые каналы с вашей командой

## Требования

- Windows 10/11
- Установленный League of Legends  
- Запущенный Discord

## Поддержка

Если возникли проблемы:
1. Убедитесь что League of Legends и Discord запущены
2. Перезапустите приложение
3. Проверьте что ваш фаерволл не блокирует приложение

## Файлы

- `LoLVoiceChat.exe` - Главное приложение
- `redis/` - Файлы сервера базы данных
- `.env` - Файл настроек

Не удаляйте никакие файлы из этой папки!
"""

    with open(os.path.join(package_dir, "README.txt"), "w", encoding="utf-8") as f:
        f.write(readme_content)
    print("✅ README создан")
    # Создаем ZIP архив
    shutil.make_archive("dist/LoLVoiceChat_v1.0.0", 'zip', package_dir)
    print("✅ ZIP архив создан: dist/LoLVoiceChat_v1.0.0.zip")


if __name__ == "__main__":
    print("🎮 Начинаем сборку LoL Voice Chat...")
    print("=" * 50)
    if build_with_workaround():
        print("\n🎉 Сборка завершена успешно!")
        print("📦 Дистрибутивный пакет: dist/LoLVoiceChat_v1.0.0.zip")
        print("🚀 Исполняемый файл: dist/LoLVoiceChat.exe")
    else:
        print("\n❌ Сборка не удалась!")
        sys.exit(1)
