"""
Build script for LoL Voice Chat with WebView
"""

import os
import shutil
import subprocess
import secrets


def clean_build():
    """Clean previous builds."""
    for dir_name in ['dist', 'build', '__pycache__', 'hooks']:
        if os.path.exists(dir_name):
            shutil.rmtree(dir_name, ignore_errors=True)
            print(f'Cleaned: {dir_name}')


def create_hooks():
    """Create hooks for PyInstaller."""
    hooks_dir = 'hooks'
    os.makedirs(hooks_dir, exist_ok=True)
    webview_hook = '''"""
PyInstaller hook for pywebview
"""

hiddenimports = [
    'pywebview.platforms.win32',
    'pywebview.platforms.cef',
    'pywebview.libs',
]
'''
    webview_hook_path = os.path.join(hooks_dir, 'hook-pywebview.py')
    with open(webview_hook_path, 'w', encoding='utf-8') as f:
        f.write(webview_hook)
    print('✅ Hook for pywebview created')
    passlib_hook = '''"""
PyInstaller hook for passlib
"""

from PyInstaller.utils.hooks import collect_submodules

hiddenimports = collect_submodules('passlib')
'''
    passlib_hook_path = os.path.join(hooks_dir, 'hook-passlib.py')
    with open(passlib_hook_path, 'w', encoding='utf-8') as f:
        f.write(passlib_hook)
    print('✅ Hook for passlib created')


def encrypt_env_file():
    """Encrypt .env file and embed it in the code."""
    print('Encrypting .env file...')
    if not os.path.exists('.env'):
        print('❌ .env file not found')
        return False
    try:
        # Read .env file
        with open('.env', 'r', encoding='utf-8') as f:
            env_content = f.read()
        # Generate encryption key
        encryption_key = secrets.token_hex(32)

        # Simple XOR encryption
        def xor_encrypt(text, key):
            encrypted = []
            key_bytes = key.encode('utf-8')
            for i, char in enumerate(text):
                key_char = key_bytes[i % len(key_bytes)]
                encrypted_char = chr(ord(char) ^ key_char)
                encrypted.append(encrypted_char)
            return ''.join(encrypted)
        # Encrypt the content
        encrypted_content = xor_encrypt(env_content, encryption_key)
        # Create Python module with encrypted data
        encrypted_module = f'''"""
Encrypted environment variables module
Generated during build process
"""

import os
import sys

ENCRYPTED_ENV = {repr(encrypted_content)}
ENCRYPTION_KEY = {repr(encryption_key)}

def decrypt_env():
    """Decrypt and load environment variables."""
    key_bytes = ENCRYPTION_KEY.encode('utf-8')
    decrypted_chars = []
    for i, char in enumerate(ENCRYPTED_ENV):
        key_char = key_bytes[i % len(key_bytes)]
        decrypted_char = chr(ord(char) ^ key_char)
        decrypted_chars.append(decrypted_char)
    decrypted_content = ''.join(decrypted_chars)
    # Parse and set environment variables
    for line in decrypted_content.split('\\n'):
        line = line.strip()
        if line and not line.startswith('#'):
            if '=' in line:
                key, value = line.split('=', 1)
                os.environ[key.strip()] = value.strip()
    return True

# Auto-load on import
if getattr(sys, 'frozen', False):
    decrypt_env()
'''
        # Save encrypted module
        with open('app/encrypted_env.py', 'w', encoding='utf-8') as f:
            f.write(encrypted_module)
        print('✅ .env encrypted and embedded in code')
        return True
    except Exception as e:
        print(f'❌ Error encrypting .env: {e}')
        return False


def build_with_pyinstaller():
    """Build with PyInstaller."""
    print('Building EXE with WebView...')
    hidden_imports = [
        # Main application
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
        'app.encrypted_env',
        # FastAPI and web
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
        # Async
        'aiohttp',
        'aiohttp.client',
        # Validation
        'pydantic',
        'pydantic_core',
        'pydantic_settings',
        # Authentication
        'passlib',
        'passlib.handlers',
        'passlib.handlers.bcrypt',
        'jose',
        'jose.constants',
        # Redis
        'redis',
        'redis.asyncio',
        # Utilities
        'dotenv',
        'websockets',
        'multipart',
        'python_multipart',
    ]
    cmd = [
        'pyinstaller',
        '--name=LoLVoiceChat',
        '--onefile',
        '--windowed',
        '--clean',
        '--add-data=app;app',
        '--add-data=static;static',
        '--additional-hooks-dir=hooks',
    ]
    icon_path = 'static/logo/icon_L.ico'
    if os.path.exists(icon_path):
        cmd.append(f'--icon={icon_path}')
        print(f'Using icon: {icon_path}')
    for imp in hidden_imports:
        cmd.append(f'--hidden-import={imp}')
    cmd.append('webview_app.py')
    print('Running PyInstaller...')
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300
        )
        if result.returncode == 0:
            exe_path = 'dist/LoLVoiceChat.exe'
            if os.path.exists(exe_path):
                size = os.path.getsize(exe_path) / (1024 * 1024)
                print(f'✅ EXE created: {exe_path} ({size:.1f} MB)')
                return True
            else:
                print('❌ EXE file not found')
                return False
        else:
            print('❌ PyInstaller error:')
            if result.stderr:
                print(result.stderr[-1000:])
            return False
    except subprocess.TimeoutExpired:
        print('❌ Build took too long')
        return False
    except Exception as e:
        print(f'❌ Build error: {e}')
        return False


def create_package():
    """Create package without .env file."""
    print('Creating package...')
    package_dir = 'dist/LoLVoiceChat_WebView'
    os.makedirs(package_dir, exist_ok=True)
    # Copy EXE
    exe_src = 'dist/LoLVoiceChat.exe'
    if os.path.exists(exe_src):
        shutil.copy2(exe_src, os.path.join(package_dir, 'LoLVoiceChat.exe'))
        print('✅ EXE copied')
    else:
        print('❌ EXE not found')
        return False
    print('✅ .env embedded in EXE (not copied separately)')
    # Create batch file
    bat_content = """@echo off
chcp 65001 >nul
title LoL Voice Chat (WebView)
echo ========================================
echo    LoL Voice Chat - Desktop App
echo ========================================
echo.
echo Starting application...
echo Please wait 5-10 seconds...
echo.
LoLVoiceChat.exe
echo.
echo Application started!
echo Window should open automatically.
pause
"""
    bat_path = os.path.join(package_dir, 'Start.bat')
    with open(bat_path, 'w', encoding='utf-8') as f:
        f.write(bat_content)
    print('✅ Start.bat created')
    # Create README
    readme_content = """# LoL Voice Chat - Desktop Application

## Installation
1. Extract all files to one folder
2. Run Start.bat or LoLVoiceChat.exe

## Features
- ✅ Built-in interface (no browser required)
- ✅ No console window
- ✅ Automatic server startup
- ✅ Full voice chat functionality

## First launch
1. Application will open window with interface
2. Link Discord account
3. Launch League of Legends
4. Join games!

## Troubleshooting
- If window doesn't open: check lol_voice_chat.log file
"""
    readme_path = os.path.join(package_dir, 'README.txt')
    with open(readme_path, 'w', encoding='utf-8') as f:
        f.write(readme_content)
    print('✅ README created')
    # Create ZIP
    import datetime
    date_str = datetime.datetime.now().strftime('%Y%m%d_%H%M')
    zip_name = f'dist/LoLVoiceChat_WebView_{date_str}'
    shutil.make_archive(zip_name, 'zip', package_dir)
    print(f'✅ ZIP created: {zip_name}.zip')
    return True


def cleanup_temp_files():
    """Clean up temporary encryption files."""
    temp_files = ['app/encrypted_env.py']
    for file in temp_files:
        if os.path.exists(file):
            os.remove(file)
            print(f'Cleaned up: {file}')


def main():
    """Main function."""
    print('🎮 Building LoL Voice Chat with WebView')
    print('=' * 50)
    # Check required files
    required_files = ['webview_app.py', '.env', 'app', 'static']
    for f in required_files:
        if not os.path.exists(f):
            print(f'❌ Missing: {f}')
            return
    clean_build()
    create_hooks()
    # Encrypt .env before building
    if not encrypt_env_file():
        print('❌ Failed to encrypt .env file')
        return
    if not build_with_pyinstaller():
        print('❌ Build failed')
        cleanup_temp_files()
        return
    if not create_package():
        print('⚠️  Package creation error')
    # Clean up temporary files
    cleanup_temp_files()
    print('\n✅ Build completed!')
    print('\n📁 Results in dist/:')
    for item in os.listdir('dist'):
        path = os.path.join('dist', item)
        if os.path.isfile(path):
            size = os.path.getsize(path) / (1024 * 1024)
            print(f'  📄 {item} ({size:.1f} MB)')
        else:
            print(f'  📁 {item}')
    print('\n🚀 For testing: dist/LoLVoiceChat_WebView/Start.bat')
    print('🔒 .env file is encrypted and embedded in EXE')
    print('=' * 50)


if __name__ == '__main__':
    main()
