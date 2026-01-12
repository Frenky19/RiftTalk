"""
Build script for LoL Voice Chat with WebView
"""

import os
import shutil
import subprocess
import secrets
import sys
from datetime import datetime


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
    # Hook for pywebview
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
    # Hook for passlib
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


def create_self_signed_cert_for_signing():
    """Create self-signed certificate for EXE signing."""
    print('Creating self-signed certificate for EXE signing...')
    cert_dir = 'signing_certs'
    os.makedirs(cert_dir, exist_ok=True)
    pfx_path = os.path.join(cert_dir, 'lolvoicechat.pfx')
    cer_path = os.path.join(cert_dir, 'lolvoicechat.cer')
    pvk_path = os.path.join(cert_dir, 'lolvoicechat.pvk')
    # Check if cert already exists
    if os.path.exists(pfx_path):
        print('✅ Self-signed certificate already exists')
        return True
    try:
        # Method 1: Try using PowerShell (Windows)
        if sys.platform == 'win32':
            print('Using PowerShell to create code signing certificate...')
            # Create certificate with PowerShell
            ps_script = f'''
$cert = New-SelfSignedCertificate -Type CodeSigningCert `
    -Subject "CN=LoLVoiceChat, O=LoL Voice Chat, C=US" `
    -KeyAlgorithm RSA `
    -KeyLength 2048 `
    -HashAlgorithm SHA256 `
    -KeyUsage DigitalSignature `
    -KeyUsageProperty Sign `
    -KeyExportPolicy Exportable `
    -NotAfter (Get-Date).AddYears(5) `
    -CertStoreLocation "Cert:\CurrentUser\My"

$certPath = "Cert:\CurrentUser\My\$($cert.Thumbprint)"
$password = ConvertTo-SecureString -String "LoLVoiceChat123" -Force -AsPlainText

Export-PfxCertificate -Cert $certPath -FilePath "{pfx_path}" -Password $password
Export-Certificate -Cert $certPath -FilePath "{cer_path}"
'''
            # Run PowerShell script
            result = subprocess.run(
                ['powershell', '-ExecutionPolicy', 'Bypass', '-Command', ps_script],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                print(f'✅ Self-signed certificate created: {pfx_path}')
                print(f'✅ Certificate file: {cer_path}')
                # Display certificate info
                info_script = f'''
$cert = Get-PfxCertificate -FilePath "{pfx_path}"
Write-Host "Certificate Information:"
Write-Host "Subject: $($cert.Subject)"
Write-Host "Thumbprint: $($cert.Thumbprint)"
Write-Host "NotAfter: $($cert.NotAfter)"
Write-Host "Issuer: $($cert.Issuer)"
'''
                subprocess.run(
                    ['powershell', '-ExecutionPolicy', 'Bypass', '-Command', info_script],
                    capture_output=False
                )
                return True
            else:
                print(f'❌ PowerShell failed: {result.stderr}')
        # Method 2: Try using OpenSSL (cross-platform)
        print('Trying OpenSSL for certificate creation...')
        # Generate private key
        subprocess.run([
            'openssl', 'genrsa', '-out', pvk_path, '2048'
        ], check=True, capture_output=True)
        # Create certificate configuration
        config_content = '''[ req ]
default_bits = 2048
prompt = no
default_md = sha256
distinguished_name = dn
x509_extensions = v3_req

[ dn ]
C = US
ST = California
L = San Francisco
O = LoL Voice Chat
CN = LoLVoiceChat

[ v3_req ]
basicConstraints = CA:FALSE
keyUsage = digitalSignature, keyEncipherment
extendedKeyUsage = codeSigning
subjectAltName = @alt_names

[ alt_names ]
DNS.1 = localhost
IP.1 = 127.0.0.1
'''
        config_path = os.path.join(cert_dir, 'cert.conf')
        with open(config_path, 'w', encoding='utf-8') as f:
            f.write(config_content)
        # Generate certificate signing request
        csr_path = os.path.join(cert_dir, 'cert.csr')
        subprocess.run([
            'openssl', 'req', '-new', '-key', pvk_path, '-out', csr_path,
            '-config', config_path
        ], check=True, capture_output=True)
        # Create self-signed certificate
        subprocess.run([
            'openssl', 'x509', '-req', '-days', '1825', '-in', csr_path,
            '-signkey', pvk_path, '-out', cer_path,
            '-extensions', 'v3_req', '-extfile', config_path
        ], check=True, capture_output=True)
        # Create PFX file
        subprocess.run([
            'openssl', 'pkcs12', '-export', '-out', pfx_path,
            '-inkey', pvk_path, '-in', cer_path,
            '-password', 'pass:LoLVoiceChat123'
        ], check=True, capture_output=True)
        # Clean up temporary files
        for temp_file in [config_path, csr_path]:
            if os.path.exists(temp_file):
                os.remove(temp_file)
        print(f'✅ Self-signed certificate created with OpenSSL: {pfx_path}')
        print('⚠️  Note: This is a self-signed certificate for testing only!')
        print('⚠️  Windows will show "Unknown Publisher" warning.')
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f'❌ Failed to create certificate: {e}')
        print('\n📝 Manual certificate creation options:')
        print('   1. Use Visual Studio Developer Command Prompt:')
        print('      makecert -r -pe -n "CN=LoLVoiceChat" -b 01/01/2023 -e 01/01/2028 -ss my')
        print('   2. Use OpenSSL (install from https://slproweb.com/products/Win32OpenSSL.html)')
        print('   3. Buy a trusted code signing certificate from:')
        print('      - DigiCert')
        print('      - Sectigo')
        print('      - GlobalSign')
        return False
    except Exception as e:
        print(f'❌ Unexpected error: {e}')
        return False


def sign_exe_file(exe_path):
    """Sign EXE file with self-signed certificate."""
    print(f'Signing EXE file: {exe_path}')
    if not os.path.exists(exe_path):
        print('❌ EXE file not found')
        return False
    pfx_path = 'signing_certs/lolvoicechat.pfx'
    if not os.path.exists(pfx_path):
        print('❌ Certificate file not found')
        return False
    try:
        # Method 1: Try signtool (Windows SDK)
        print('Trying to sign with signtool...')
        # Common signtool paths
        signtool_paths = [
            r'C:\Program Files (x86)\Windows Kits\10\bin\10.0.22621.0\x64\signtool.exe',
            r'C:\Program Files (x86)\Windows Kits\10\bin\10.0.22621.0\x86\signtool.exe',
            r'C:\Program Files (x86)\Windows Kits\10\bin\x64\signtool.exe',
            r'C:\Program Files (x86)\Windows Kits\10\bin\x86\signtool.exe',
            r'C:\Program Files (x86)\Microsoft SDKs\Windows\v7.1A\Bin\signtool.exe',
            'signtool.exe'
        ]
        signtool = None
        for path in signtool_paths:
            if os.path.exists(path):
                signtool = path
                break
        if signtool:
            # First, try to sign with timestamp
            timestamp_urls = [
                'http://timestamp.digicert.com',
                'http://timestamp.sectigo.com',
                'http://timestamp.globalsign.com',
                'http://timestamp.comodoca.com'
            ]
            for timestamp_url in timestamp_urls:
                try:
                    cmd = [
                        signtool, 'sign',
                        '/f', pfx_path,
                        '/p', 'LoLVoiceChat123',
                        '/fd', 'SHA256',
                        '/tr', timestamp_url,
                        '/td', 'SHA256',
                        '/du', 'https://github.com/LoLVoiceChat',
                        exe_path
                    ]
                    print(f'Signing with timestamp server: {timestamp_url}')
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=60
                    )
                    if result.returncode == 0:
                        print('✅ EXE signed successfully with timestamp')
                        # Verify the signature
                        verify_cmd = [signtool, 'verify', '/pa', '/v', exe_path]
                        verify_result = subprocess.run(
                            verify_cmd,
                            capture_output=True,
                            text=True
                        )
                        if verify_result.returncode == 0:
                            print('✅ Signature verified successfully')
                            print(verify_result.stdout)
                        else:
                            print('⚠️  Signature verification warning')
                            print(verify_result.stderr)
                        return True
                    else:
                        print(f'❌ Timestamp signing failed: {result.stderr}')
                except subprocess.TimeoutExpired:
                    print(f'❌ Timestamp server timeout: {timestamp_url}')
                    continue
                except Exception as e:
                    print(f'❌ Error with timestamp server: {e}')
                    continue
            # If timestamp servers fail, sign without timestamp
            print('Trying to sign without timestamp...')
            cmd = [
                signtool, 'sign',
                '/f', pfx_path,
                '/p', 'LoLVoiceChat123',
                '/fd', 'SHA256',
                '/du', 'https://github.com/LoLVoiceChat',
                exe_path
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                print('✅ EXE signed successfully (no timestamp)')
                return True
            else:
                print(f'❌ Signing failed: {result.stderr}')
        # Method 2: Try osslsigncode (cross-platform)
        print('Trying osslsigncode...')
        try:
            # First sign without timestamp
            cmd = [
                'osslsigncode', 'sign',
                '-pkcs12', pfx_path,
                '-pass', 'LoLVoiceChat123',
                '-n', 'LoL Voice Chat',
                '-i', 'https://github.com/LoLVoiceChat',
                '-in', exe_path,
                '-out', exe_path + '.signed'
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                # Replace original with signed version
                os.remove(exe_path)
                shutil.move(exe_path + '.signed', exe_path)
                print('✅ EXE signed with osslsigncode')
                return True
            else:
                print(f'❌ osslsigncode failed: {result.stderr}')
        except (subprocess.CalledProcessError, FileNotFoundError):
            print('❌ osslsigncode not available')
        print('❌ No signing tool available')
        print('\n📝 Manual signing options:')
        print('   1. Install Windows SDK: https://developer.microsoft.com/en-us/windows/downloads/windows-sdk/')
        print('   2. Install osslsigncode: https://github.com/mtrojnar/osslsigncode')
        print('   3. Use online signing service')
        return False
    except Exception as e:
        print(f'❌ Signing error: {e}')
        return False


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
                return exe_path
            else:
                print('❌ EXE file not found')
                return None
        else:
            print('❌ PyInstaller error:')
            if result.stderr:
                print(result.stderr[-1000:])
            return None
    except subprocess.TimeoutExpired:
        print('❌ Build took too long')
        return None
    except Exception as e:
        print(f'❌ Build error: {e}')
        return None


def create_package(exe_path):
    """Create package without .env file and without certificate files."""
    print('Creating package...')
    package_dir = 'dist/LoLVoiceChat_WebView'
    os.makedirs(package_dir, exist_ok=True)
    # Copy EXE
    if os.path.exists(exe_path):
        shutil.copy2(exe_path, os.path.join(package_dir, 'LoLVoiceChat.exe'))
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
echo Note: Windows may show "Unknown Publisher" warning.
echo       This is normal for self-signed applications.
echo       Click "More info" -> "Run anyway" to continue.
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
    readme_content = """# Rift Talk - Desktop Application

## Installation
1. Extract all files to one folder
2. Run Start.bat or LoLVoiceChat.exe

## Security Note
- This app is signed with a self-signed certificate
- Windows will show "Unknown Publisher" warning
- This is NORMAL for self-signed applications
- Click "More info" → "Run anyway" to continue

## Features
- ✅ Built-in interface (no browser required)
- ✅ Digitally signed EXE (self-signed)
- ✅ No console window
- ✅ Automatic server startup
- ✅ Full voice chat functionality

## First launch
1. Accept security warning if shown
2. Application will open window with interface
3. Link Discord account
4. Launch League of Legends
5. Join games!

## Troubleshooting
- If window doesn't open: check lol_voice_chat.log file
- Security warning: This is expected, click "Run anyway"
- If blocked by SmartScreen: Click "More info" → "Run anyway"
"""
    readme_path = os.path.join(package_dir, 'README.txt')
    with open(readme_path, 'w', encoding='utf-8') as f:
        f.write(readme_content)
    print('✅ README created')
    # Create ZIP
    date_str = datetime.now().strftime('%Y%m%d_%H%M')
    zip_name = f'dist/LoLVoiceChat_WebView_{date_str}'
    shutil.make_archive(zip_name, 'zip', package_dir)
    print(f'✅ ZIP created: {zip_name}.zip')
    return True


def cleanup_temp_files():
    """Clean up temporary files."""
    temp_files = [
        'app/encrypted_env.py',
    ]
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
    # Create self-signed certificate for code signing
    print('\n🔐 Creating self-signed certificate for EXE signing...')
    if not create_self_signed_cert_for_signing():
        print('⚠️  Certificate creation failed, continuing without signing...')
        print('⚠️  EXE will show "Unknown Publisher" warning')
        signing_enabled = False
    else:
        signing_enabled = True
    # Encrypt .env before building
    if not encrypt_env_file():
        print('❌ Failed to encrypt .env file')
        cleanup_temp_files()
        return
    # Build EXE
    exe_path = build_with_pyinstaller()
    if not exe_path:
        print('❌ Build failed')
        cleanup_temp_files()
        return
    # Sign EXE if certificate was created
    if signing_enabled:
        print('\n📝 Signing EXE file...')
        if not sign_exe_file(exe_path):
            print('⚠️  EXE signing failed, continuing without signature...')
            print('⚠️  Windows will show stronger security warning')
        else:
            print('✅ EXE signed successfully')
    else:
        print('⚠️  Skipping EXE signing (no certificate available)')
    # Create package
    if not create_package(exe_path):
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
    if signing_enabled:
        print('🔐 EXE is signed with self-signed certificate')
        print('⚠️  Windows will show "Unknown Publisher" warning')
        print('📋 Certificate files in signing_certs/ folder')
        print('📝 Install lolvoicechat.cer to "Trusted Publishers" to avoid warning')
    else:
        print('⚠️  EXE is NOT signed - strong security warning expected')
    print('=' * 50)


if __name__ == '__main__':
    main()
