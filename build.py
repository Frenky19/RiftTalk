"""
Исправленный build script для LoL Voice Chat - Windows с hooks
"""

import os
import sys
import shutil
import subprocess


def clean_build_dirs():
    """Очистка папок сборки"""
    dirs_to_clean = ['dist', 'build', '__pycache__']
    for dir_name in dirs_to_clean:
        if os.path.exists(dir_name):
            shutil.rmtree(dir_name, ignore_errors=True)
            print(f"✅ Очищено: {dir_name}")


def build_with_hooks():
    """Сборка с использованием hooks"""
    print("🔨 Запускаем сборку с hooks...")
    
    # Создаем папку для hooks если её нет
    hooks_dir = 'hooks'
    os.makedirs(hooks_dir, exist_ok=True)
    
    # Создаем базовую команду
    cmd = [
        'pyinstaller',
        '--name=LoLVoiceChat',
        '--onefile',
        '--console',
        '--clean',
        '--add-data=app;app',
        '--add-data=static;static',
        '--add-data=.env;.',
        '--additional-hooks-dir=hooks',
    ]
    
    # Добавляем hidden imports
    hidden_imports = [
        # FastAPI и веб
        'uvicorn.lifespan.on', 'uvicorn.lifespan.off', 'uvicorn.loops.auto',
        'uvicorn.protocols.http', 'uvicorn.protocols.websockets', 'uvicorn.logging',
        
        # Наше приложение
        'app.main', 'app.config', 'app.database', 'app.models', 'app.schemas',
        'app.utils.exceptions', 'app.utils.security', 'app.utils.logger',
        'app.utils.lcu_connector', 'app.services.lcu_service', 'app.services.discord_service',
        'app.services.voice_service', 'app.services.cleanup_service', 'app.endpoints.voice',
        'app.endpoints.auth', 'app.endpoints.lcu', 'app.endpoints.discord', 'app.endpoints.demo',
        'app.middleware.demo_auth',
        
        # Сторонние библиотеки
        'pydantic', 'pydantic_core', 'pydantic_settings',
        'dotenv', 'discord', 'aiohttp', 'python_jose', 'passlib',
        'bcrypt', 'fastapi', 'starlette', 'websockets', 'python_multipart',
        'jinja2', 'click', 'anyio', 'httpx', 'jose', 'cryptography',
        'requests',
        
        # Критически важные подмодули
        'passlib.handlers', 'passlib.handlers.bcrypt', 'passlib.handlers.sha2_crypt',
        'passlib.handlers.pbkdf2', 'passlib.handlers.argon2', 'passlib.handlers.django',
        'passlib.handlers.md5_crypt', 'passlib.handlers.des_crypt',
    ]
    
    for imp in hidden_imports:
        cmd.append(f'--hidden-import={imp}')
    
    # Добавляем основной файл
    cmd.append('launcher.py')
    
    try:
        print("🚀 Запускаем PyInstaller с hooks...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        if result.returncode == 0:
            # Проверяем результат
            exe_path = 'dist/LoLVoiceChat.exe'
            if os.path.exists(exe_path):
                print(f"✅ Исполняемый файл создан: {exe_path}")
                return True
            else:
                print("❌ Исполняемый файл не найден")
                return False
        else:
            print(f"❌ Ошибка сборки (код: {result.returncode})")
            if result.stderr:
                print("=== STDERR ===")
                print(result.stderr)
            return False
            
    except subprocess.TimeoutExpired:
        print("❌ Сборка заняла слишком много времени")
        return False
    except Exception as e:
        print(f"❌ Ошибка сборки: {e}")
        return False


def create_distribution_package():
    """Создание дистрибутивного пакета"""
    print("📦 Создаем дистрибутивный пакет...")
    
    package_dir = "dist/LoLVoiceChat_Package"
    os.makedirs(package_dir, exist_ok=True)
    
    # Копируем исполняемый файл
    exe_src = "dist/LoLVoiceChat.exe"
    if os.path.exists(exe_src):
        shutil.copy2(exe_src, os.path.join(package_dir, "LoLVoiceChat.exe"))
        print("✅ Исполняемый файл скопирован")
    else:
        print("❌ Исполняемый файл не найден")
        return False
    
    # Копируем .env файл
    if os.path.exists('.env'):
        shutil.copy2('.env', package_dir)
        print("✅ .env файл скопирован")
    
    # Копируем папку static
    if os.path.exists('static'):
        shutil.copytree('static', os.path.join(package_dir, 'static'), dirs_exist_ok=True)
        print("✅ Static папка скопирована")
    
    # Создаем README
    readme_content = """# LoL Voice Chat - Windows Application

## Установка и запуск

1. **Распакуйте** этот ZIP файл в любую папку
2. **Запустите** `LoLVoiceChat.exe` или `Start.bat`
3. **Приложение автоматически:**
   - Запустит сервер голосового чата
   - Откроет браузер со страницей настройки
   - Создаст файл логов `lol_voice_chat.log`

## Особенности

- ✅ **Не требует Redis** - использует встроенное хранилище
- ✅ **Автозапуск** - все запускается автоматически
- ✅ **Полная функциональность** - все возможности голосового чата

## Требования

- Windows 10/11
- Установленный League of Legends
- Запущенный Discord
- Доступ к интернету

## Устранение проблем

### Если приложение не запускается:
1. Проверьте файл `lol_voice_chat.log`
2. Убедитесь что порт 8000 свободен
3. Попробуйте запустить от имени администратора

## Важно!

- Не удаляйте файлы из папки приложения
- Закрывайте приложение через Ctrl+C в консоли
- Для полной остановки закройте окно консоли
"""

    with open(os.path.join(package_dir, "README.txt"), "w", encoding="utf-8") as f:
        f.write(readme_content)
    print("✅ README создан")
    
    # Создаем BAT файл для запуска
    bat_content = """@echo off
chcp 65001 >nul
title LoL Voice Chat
echo ========================================
echo    LoL Voice Chat - Запуск приложения
echo ========================================
echo.
echo Запуск приложения...
echo.
LoLVoiceChat.exe
pause
"""
    
    with open(os.path.join(package_dir, "Start.bat"), "w", encoding="utf-8") as f:
        f.write(bat_content)
    print("✅ BAT файл создан")
    
    # Создаем ZIP архив
    shutil.make_archive("dist/LoLVoiceChat_v1.0.0", 'zip', package_dir)
    print("✅ ZIP архив создан: dist/LoLVoiceChat_v1.0.0.zip")
    
    return True


def main():
    """Главная функция сборки"""
    print("🎮 Сборка LoL Voice Chat для Windows")
    print("=" * 50)
    
    # Очистка
    print("🗑️ Очистка предыдущих сборок...")
    clean_build_dirs()
    
    # Создаем hook для passlib
    print("🔧 Создаем hooks для PyInstaller...")
    hooks_dir = 'hooks'
    os.makedirs(hooks_dir, exist_ok=True)
    
    hook_content = '''"""
PyInstaller hook for passlib
"""

from PyInstaller.utils.hooks import collect_submodules

# Включаем все подмодули passlib
hiddenimports = collect_submodules('passlib')
'''
    
    with open(os.path.join(hooks_dir, 'hook-passlib.py'), 'w', encoding='utf-8') as f:
        f.write(hook_content)
    print("✅ Hook для passlib создан")
    
    # Прямая сборка с hooks
    print("🔨 Запуск сборки с hooks...")
    if build_with_hooks():
        print("\n✅ Сборка завершена успешно!")
        
        # Создаем пакет
        if create_distribution_package():
            print("\n🎉 Дистрибутив создан успешно!")
            print("📦 Пакет: dist/LoLVoiceChat_v1.0.0.zip")
            print("🚀 Исполняемый файл: dist/LoLVoiceChat.exe")
            print("\n💡 Запустите Start.bat из папки пакета для тестирования")
        else:
            print("❌ Ошибка создания пакета")
    else:
        print("\n❌ Сборка не удалась!")
        sys.exit(1)


if __name__ == "__main__":
    main()