#!/usr/bin/env python3
"""
Build script для LoL Voice Chat с WebView
"""

import os
import sys
import shutil
import subprocess

def clean_build():
    """Очистка предыдущих сборок"""
    for dir_name in ['dist', 'build', '__pycache__', 'hooks']:
        if os.path.exists(dir_name):
            shutil.rmtree(dir_name, ignore_errors=True)
            print(f"Очищено: {dir_name}")

def create_hooks():
    """Создание hooks для PyInstaller"""
    hooks_dir = 'hooks'
    os.makedirs(hooks_dir, exist_ok=True)
    
    # Hook для pywebview
    webview_hook = '''"""
PyInstaller hook for pywebview
"""

hiddenimports = [
    'pywebview.platforms.win32',
    'pywebview.platforms.cef',
    'pywebview.libs',
]
'''
    
    with open(os.path.join(hooks_dir, 'hook-pywebview.py'), 'w', encoding='utf-8') as f:
        f.write(webview_hook)
    print("✅ Hook для pywebview создан")
    
    # Hook для passlib
    passlib_hook = '''"""
PyInstaller hook for passlib
"""

from PyInstaller.utils.hooks import collect_submodules

hiddenimports = collect_submodules('passlib')
'''
    
    with open(os.path.join(hooks_dir, 'hook-passlib.py'), 'w', encoding='utf-8') as f:
        f.write(passlib_hook)
    print("✅ Hook для passlib создан")

def build_with_pyinstaller():
    """Сборка с PyInstaller"""
    print("Сборка EXE с WebView...")
    
    # Основные скрытые импорты
    hidden_imports = [
        # Основное приложение
        'app',
        'app.main',
        'app.config',
        'app.database',
        'app.models',
        'app.schemas',
        'app.utils',
        'app.services',
        'app.endpoints',
        'app.middleware',
        
        # FastAPI и веб
        'fastapi',
        'fastapi.staticfiles',
        'starlette',
        'uvicorn',
        'uvicorn.lifespan.on',
        'uvicorn.lifespan.off',
        
        # Discord
        'discord',
        'discord.voice_client',
        
        # WebView
        'pywebview',
        'pywebview.platforms.win32',
        
        # Асинхронность
        'aiohttp',
        'aiohttp.client',
        
        # Валидация
        'pydantic',
        'pydantic_core',
        'pydantic_settings',
        
        # Авторизация
        'passlib',
        'passlib.handlers',
        'passlib.handlers.bcrypt',
        'jose',
        'jose.constants',
        
        # Redis
        'redis',
        'redis.asyncio',
        
        # Утилиты
        'dotenv',
        'websockets',
        'multipart',
        'python_multipart',
    ]
    
    # Команда PyInstaller
    cmd = [
        'pyinstaller',
        '--name=LoLVoiceChat',
        '--onefile',
        '--windowed',  # Без консоли
        '--clean',
        '--add-data=app;app',
        '--add-data=static;static',
        '--add-data=.env;.',
        '--additional-hooks-dir=hooks',
    ]
    
    # Добавляем иконку если есть
    icon_path = 'static/logo/icon_L.ico'
    if os.path.exists(icon_path):
        cmd.append(f'--icon={icon_path}')
        print(f"Используется иконка: {icon_path}")
    
    # Добавляем скрытые импорты
    for imp in hidden_imports:
        cmd.append(f'--hidden-import={imp}')
    
    # Точка входа
    cmd.append('webview_app.py')
    
    print(f"Запуск PyInstaller...")
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        if result.returncode == 0:
            exe_path = 'dist/LoLVoiceChat.exe'
            if os.path.exists(exe_path):
                size = os.path.getsize(exe_path) / (1024 * 1024)
                print(f"✅ EXE создан: {exe_path} ({size:.1f} MB)")
                return True
            else:
                print("❌ EXE файл не найден")
                return False
        else:
            print("❌ Ошибка PyInstaller:")
            if result.stderr:
                print(result.stderr[-1000:])
            return False
            
    except subprocess.TimeoutExpired:
        print("❌ Сборка заняла слишком много времени")
        return False
    except Exception as e:
        print(f"❌ Ошибка сборки: {e}")
        return False

def create_package():
    """Создание пакета"""
    print("Создание пакета...")
    
    package_dir = "dist/LoLVoiceChat_WebView"
    os.makedirs(package_dir, exist_ok=True)
    
    # Копируем EXE
    exe_src = "dist/LoLVoiceChat.exe"
    if os.path.exists(exe_src):
        shutil.copy2(exe_src, os.path.join(package_dir, "LoLVoiceChat.exe"))
        print("✅ EXE скопирован")
    else:
        print("❌ EXE не найден")
        return False
    
    # Копируем .env
    if os.path.exists('.env'):
        shutil.copy2('.env', package_dir)
        print("✅ .env скопирован")
    
    # Создаем батник
    bat_content = """@echo off
chcp 65001 >nul
title LoL Voice Chat (WebView)
echo ========================================
echo    LoL Voice Chat - Desktop App
echo ========================================
echo.
echo Запуск приложения...
echo Ожидайте 5-10 секунд...
echo.
LoLVoiceChat.exe
echo.
echo Приложение запущено!
echo Окно должно открыться автоматически.
pause
"""
    
    with open(os.path.join(package_dir, "Start.bat"), "w", encoding="utf-8") as f:
        f.write(bat_content)
    print("✅ Start.bat создан")
    
    # Создаем README
    readme_content = """# LoL Voice Chat - Desktop Application

## Установка
1. Распакуйте все файлы в одну папку
2. Запустите Start.bat или LoLVoiceChat.exe

## Особенности
- ✅ Встроенный интерфейс (не требуется браузер)
- ✅ Без консоли
- ✅ Автоматический запуск сервера
- ✅ Полный функционал голосового чата

## Первый запуск
1. Приложение откроет окно с интерфейсом
2. Привяжите Discord аккаунт
3. Запустите League of Legends
4. Присоединяйтесь к играм!

## Устранение проблем
- Если окно не открывается: проверьте файл lol_voice_chat.log
- Убедитесь что .env файл присутствует
- Проверьте настройки Discord бота
"""
    
    with open(os.path.join(package_dir, "README.txt"), "w", encoding="utf-8") as f:
        f.write(readme_content)
    print("✅ README создан")
    
    # Создаем ZIP
    import datetime
    date_str = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    zip_name = f"dist/LoLVoiceChat_WebView_{date_str}"
    
    shutil.make_archive(zip_name, 'zip', package_dir)
    print(f"✅ ZIP создан: {zip_name}.zip")
    
    return True

def main():
    """Главная функция"""
    print("🎮 Сборка LoL Voice Chat с WebView")
    print("=" * 50)
    
    # Проверка файлов
    required_files = ['webview_app.py', '.env', 'app', 'static']
    for f in required_files:
        if not os.path.exists(f):
            print(f"❌ Отсутствует: {f}")
            return
    
    # Очистка
    clean_build()
    
    # Создание hooks
    create_hooks()
    
    # Сборка
    if not build_with_pyinstaller():
        print("❌ Сборка не удалась")
        return
    
    # Пакет
    if not create_package():
        print("⚠️  Ошибка создания пакета")
    
    print("\n✅ Сборка завершена!")
    print("\n📁 Результаты в dist/:")
    for item in os.listdir('dist'):
        path = os.path.join('dist', item)
        if os.path.isfile(path):
            size = os.path.getsize(path) / (1024 * 1024)
            print(f"  📄 {item} ({size:.1f} MB)")
        else:
            print(f"  📁 {item}")
    
    print("\n🚀 Для тестирования: dist/LoLVoiceChat_WebView/Start.bat")
    print("=" * 50)

if __name__ == "__main__":
    main()