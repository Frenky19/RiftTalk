"""
Build script for RiftTalk with WebView
"""

import os
import shutil
import subprocess
import secrets
import sys
from datetime import datetime


APP_NAME = "RiftTalk"
EXE_NAME = f"{APP_NAME}.exe"
PACKAGE_DIR_NAME = f"{APP_NAME}_WebView"
CERT_BASENAME = "rifttalk"
CERT_PASSWORD = "RiftTalk123"


def clean_build():
    """Clean previous builds."""
    for dir_name in ["dist", "build", "__pycache__", "hooks"]:
        if os.path.exists(dir_name):
            shutil.rmtree(dir_name, ignore_errors=True)
            print(f"Cleaned: {dir_name}")


def create_hooks():
    """Create hooks for PyInstaller."""
    hooks_dir = "hooks"
    os.makedirs(hooks_dir, exist_ok=True)
    # Hook for pywebview
    webview_hook = """\"\"\"
PyInstaller hook for pywebview
\"\"\"

hiddenimports = [
    "pywebview.platforms.win32",
    "pywebview.platforms.cef",
    "pywebview.libs",
]
"""
    webview_hook_path = os.path.join(hooks_dir, "hook-pywebview.py")
    with open(webview_hook_path, "w", encoding="utf-8") as f:
        f.write(webview_hook)
    print("✅ Hook for pywebview created")
    # Hook for passlib
    passlib_hook = """\"\"\"
PyInstaller hook for passlib
\"\"\"

from PyInstaller.utils.hooks import collect_submodules

hiddenimports = collect_submodules("passlib")
"""
    passlib_hook_path = os.path.join(hooks_dir, "hook-passlib.py")
    with open(passlib_hook_path, "w", encoding="utf-8") as f:
        f.write(passlib_hook)
    print("✅ Hook for passlib created")


def create_self_signed_cert_for_signing():
    """Create self-signed certificate for EXE signing."""
    print("Creating self-signed certificate for EXE signing...")
    cert_dir = "signing_certs"
    os.makedirs(cert_dir, exist_ok=True)
    pfx_path = os.path.join(cert_dir, f"{CERT_BASENAME}.pfx")
    cer_path = os.path.join(cert_dir, f"{CERT_BASENAME}.cer")
    pvk_path = os.path.join(cert_dir, f"{CERT_BASENAME}.pvk")
    if os.path.exists(pfx_path):
        print("✅ Self-signed certificate already exists")
        return True
    try:
        # Method 1: PowerShell (Windows)
        if sys.platform == "win32":
            print("Using PowerShell to create code signing certificate...")
            ps_script = f"""
$cert = New-SelfSignedCertificate -Type CodeSigningCert `
    -Subject "CN={APP_NAME}, O={APP_NAME}, C=US" `
    -KeyAlgorithm RSA `
    -KeyLength 2048 `
    -HashAlgorithm SHA256 `
    -KeyUsage DigitalSignature `
    -KeyUsageProperty Sign `
    -KeyExportPolicy Exportable `
    -NotAfter (Get-Date).AddYears(5) `
    -CertStoreLocation "Cert:\\CurrentUser\\My"

$certPath = "Cert:\\CurrentUser\\My\\$($cert.Thumbprint)"
$password = ConvertTo-SecureString -String "{CERT_PASSWORD}" -Force -AsPlainText

Export-PfxCertificate -Cert $certPath -FilePath "{pfx_path}" -Password $password
Export-Certificate -Cert $certPath -FilePath "{cer_path}"
"""
            result = subprocess.run(
                ["powershell", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                print(f"✅ Self-signed certificate created: {pfx_path}")
                print(f"✅ Certificate file: {cer_path}")

                info_script = f"""
$cert = Get-PfxCertificate -FilePath "{pfx_path}"
Write-Host "Certificate Information:"
Write-Host "Subject: $($cert.Subject)"
Write-Host "Thumbprint: $($cert.Thumbprint)"
Write-Host "NotAfter: $($cert.NotAfter)"
Write-Host "Issuer: $($cert.Issuer)"
"""
                subprocess.run(
                    ["powershell", "-ExecutionPolicy", "Bypass", "-Command", info_script],
                    capture_output=False,
                )
                return True
            else:
                print(f"❌ PowerShell failed: {result.stderr}")
        # Method 2: OpenSSL
        print("Trying OpenSSL for certificate creation...")
        subprocess.run(["openssl", "genrsa", "-out", pvk_path, "2048"], check=True, capture_output=True)
        config_content = f"""[ req ]
default_bits = 2048
prompt = no
default_md = sha256
distinguished_name = dn
x509_extensions = v3_req

[ dn ]
C = US
ST = California
L = San Francisco
O = {APP_NAME}
CN = {APP_NAME}

[ v3_req ]
basicConstraints = CA:FALSE
keyUsage = digitalSignature, keyEncipherment
extendedKeyUsage = codeSigning
subjectAltName = @alt_names

[ alt_names ]
DNS.1 = localhost
IP.1 = 127.0.0.1
"""
        config_path = os.path.join(cert_dir, "cert.conf")
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(config_content)
        csr_path = os.path.join(cert_dir, "cert.csr")
        subprocess.run(
            ["openssl", "req", "-new", "-key", pvk_path, "-out", csr_path, "-config", config_path],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "openssl",
                "x509",
                "-req",
                "-days",
                "1825",
                "-in",
                csr_path,
                "-signkey",
                pvk_path,
                "-out",
                cer_path,
                "-extensions",
                "v3_req",
                "-extfile",
                config_path,
            ],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "openssl",
                "pkcs12",
                "-export",
                "-out",
                pfx_path,
                "-inkey",
                pvk_path,
                "-in",
                cer_path,
                "-password",
                f"pass:{CERT_PASSWORD}",
            ],
            check=True,
            capture_output=True,
        )
        for temp_file in [config_path, csr_path]:
            if os.path.exists(temp_file):
                os.remove(temp_file)
        print(f"✅ Self-signed certificate created with OpenSSL: {pfx_path}")
        print("⚠️  Note: This is a self-signed certificate for testing only!")
        print('⚠️  Windows will show "Unknown Publisher" warning.')
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"❌ Failed to create certificate: {e}")
        print("\n📝 Manual certificate creation options:")
        print("   1. Use Visual Studio Developer Command Prompt:")
        print('      makecert -r -pe -n "CN=RiftTalk" -b 01/01/2023 -e 01/01/2028 -ss my')
        print("   2. Use OpenSSL (install Win64 OpenSSL)")
        print("   3. Buy a trusted code signing certificate from DigiCert / Sectigo / GlobalSign")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False


def sign_exe_file(exe_path: str) -> bool:
    """Sign EXE file with self-signed certificate."""
    print(f"Signing EXE file: {exe_path}")
    if not os.path.exists(exe_path):
        print("❌ EXE file not found")
        return False
    pfx_path = os.path.join("signing_certs", f"{CERT_BASENAME}.pfx")
    if not os.path.exists(pfx_path):
        print("❌ Certificate file not found")
        return False
    try:
        print("Trying to sign with signtool...")
        signtool_paths = [
            r"C:\Program Files (x86)\Windows Kits\10\bin\10.0.22621.0\x64\signtool.exe",
            r"C:\Program Files (x86)\Windows Kits\10\bin\10.0.22621.0\x86\signtool.exe",
            r"C:\Program Files (x86)\Windows Kits\10\bin\x64\signtool.exe",
            r"C:\Program Files (x86)\Windows Kits\10\bin\x86\signtool.exe",
            r"C:\Program Files (x86)\Microsoft SDKs\Windows\v7.1A\Bin\signtool.exe",
            "signtool.exe",
        ]
        signtool = None
        for path in signtool_paths:
            if os.path.exists(path):
                signtool = path
                break
        du_url = "https://github.com/LoLVoiceChat"  # change if you have a real project URL
        if signtool:
            timestamp_urls = [
                "http://timestamp.digicert.com",
                "http://timestamp.sectigo.com",
                "http://timestamp.globalsign.com",
                "http://timestamp.comodoca.com",
            ]
            for timestamp_url in timestamp_urls:
                try:
                    cmd = [
                        signtool,
                        "sign",
                        "/f",
                        pfx_path,
                        "/p",
                        CERT_PASSWORD,
                        "/fd",
                        "SHA256",
                        "/tr",
                        timestamp_url,
                        "/td",
                        "SHA256",
                        "/du",
                        du_url,
                        exe_path,
                    ]
                    print(f"Signing with timestamp server: {timestamp_url}")
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                    if result.returncode == 0:
                        print("✅ EXE signed successfully with timestamp")
                        verify_cmd = [signtool, "verify", "/pa", "/v", exe_path]
                        verify_result = subprocess.run(verify_cmd, capture_output=True, text=True)
                        if verify_result.returncode == 0:
                            print("✅ Signature verified successfully")
                            print(verify_result.stdout)
                        else:
                            print("⚠️  Signature verification warning")
                            print(verify_result.stderr)
                        return True
                    else:
                        print(f"❌ Timestamp signing failed: {result.stderr}")
                except subprocess.TimeoutExpired:
                    print(f"❌ Timestamp server timeout: {timestamp_url}")
                    continue
                except Exception as e:
                    print(f"❌ Error with timestamp server: {e}")
                    continue
            print("Trying to sign without timestamp...")
            cmd = [
                signtool,
                "sign",
                "/f",
                pfx_path,
                "/p",
                CERT_PASSWORD,
                "/fd",
                "SHA256",
                "/du",
                du_url,
                exe_path,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                print("✅ EXE signed successfully (no timestamp)")
                return True
            else:
                print(f"❌ Signing failed: {result.stderr}")
        print("Trying osslsigncode...")
        try:
            cmd = [
                "osslsigncode",
                "sign",
                "-pkcs12",
                pfx_path,
                "-pass",
                CERT_PASSWORD,
                "-n",
                APP_NAME,
                "-i",
                du_url,
                "-in",
                exe_path,
                "-out",
                exe_path + ".signed",
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                os.remove(exe_path)
                shutil.move(exe_path + ".signed", exe_path)
                print("✅ EXE signed with osslsigncode")
                return True
            else:
                print(f"❌ osslsigncode failed: {result.stderr}")
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("❌ osslsigncode not available")

        print("❌ No signing tool available")
        print("\n📝 Manual signing options:")
        print("   1. Install Windows SDK (signtool)")
        print("   2. Install osslsigncode")
        return False
    except Exception as e:
        print(f"❌ Signing error: {e}")
        return False


def encrypt_env_file() -> bool:
    """Encrypt .env file and embed it in the code."""
    print("Encrypting .env file...")
    if not os.path.exists(".env"):
        print("❌ .env file not found")
        return False
    try:
        with open(".env", "r", encoding="utf-8") as f:
            env_content = f.read()
        encryption_key = secrets.token_hex(32)

        def xor_encrypt(text: str, key: str) -> str:
            encrypted = []
            key_bytes = key.encode("utf-8")
            for i, char in enumerate(text):
                key_char = key_bytes[i % len(key_bytes)]
                encrypted_char = chr(ord(char) ^ key_char)
                encrypted.append(encrypted_char)
            return "".join(encrypted)

        encrypted_content = xor_encrypt(env_content, encryption_key)
        encrypted_module = f"""\"\"\"
Encrypted environment variables module
Generated during build process
\"\"\"

import os
import sys

ENCRYPTED_ENV = {repr(encrypted_content)}
ENCRYPTION_KEY = {repr(encryption_key)}

def decrypt_env():
    \"\"\"Decrypt and load environment variables.\"\"\"
    key_bytes = ENCRYPTION_KEY.encode("utf-8")
    decrypted_chars = []
    for i, char in enumerate(ENCRYPTED_ENV):
        key_char = key_bytes[i % len(key_bytes)]
        decrypted_char = chr(ord(char) ^ key_char)
        decrypted_chars.append(decrypted_char)
    decrypted_content = "".join(decrypted_chars)

    for line in decrypted_content.split("\\n"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip()
    return True

if getattr(sys, "frozen", False):
    decrypt_env()
"""
        with open("app/encrypted_env.py", "w", encoding="utf-8") as f:
            f.write(encrypted_module)
        print("✅ .env encrypted and embedded in code")
        return True
    except Exception as e:
        print(f"❌ Error encrypting .env: {e}")
        return False


def build_with_pyinstaller():
    """Build with PyInstaller."""
    print("Building EXE with WebView...")
    hidden_imports = [
        "app",
        "app.main",
        "app.config",
        "app.database",
        "app.models",
        "app.schemas",
        "app.utils",
        "app.services",
        "app.endpoints",
        "app.middleware",
        "app.encrypted_env",
        "fastapi",
        "fastapi.staticfiles",
        "starlette",
        "uvicorn",
        "uvicorn.lifespan.on",
        "uvicorn.lifespan.off",
        "discord",
        "discord.voice_client",
        "pywebview",
        "pywebview.platforms.win32",
        "aiohttp",
        "aiohttp.client",
        "pydantic",
        "pydantic_core",
        "pydantic_settings",
        "passlib",
        "passlib.handlers",
        "passlib.handlers.bcrypt",
        "jose",
        "jose.constants",
        "redis",
        "redis.asyncio",
        "dotenv",
        "websockets",
        "multipart",
        "python_multipart",
    ]
    cmd = [
        "pyinstaller",
        f"--name={APP_NAME}",
        "--onefile",
        "--windowed",
        "--clean",
        "--add-data=app;app",
        "--add-data=static;static",
        "--additional-hooks-dir=hooks",
    ]
    icon_path = "static/logo/icon_L.ico"
    if os.path.exists(icon_path):
        cmd.append(f"--icon={icon_path}")
        print(f"Using icon: {icon_path}")
    for imp in hidden_imports:
        cmd.append(f"--hidden-import={imp}")
    cmd.append("webview_app.py")
    print("Running PyInstaller...")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            exe_path = os.path.join("dist", EXE_NAME)
            if os.path.exists(exe_path):
                size = os.path.getsize(exe_path) / (1024 * 1024)
                print(f"✅ EXE created: {exe_path} ({size:.1f} MB)")
                return exe_path
            print("❌ EXE file not found")
            return None
        print("❌ PyInstaller error:")
        if result.stderr:
            print(result.stderr[-1000:])
        return None
    except subprocess.TimeoutExpired:
        print("❌ Build took too long")
        return None
    except Exception as e:
        print(f"❌ Build error: {e}")
        return None


def create_package(exe_path: str) -> bool:
    """Create package without .env file and without certificate files."""
    print("Creating package...")
    package_dir = os.path.join("dist", PACKAGE_DIR_NAME)
    os.makedirs(package_dir, exist_ok=True)
    if os.path.exists(exe_path):
        shutil.copy2(exe_path, os.path.join(package_dir, EXE_NAME))
        print("✅ EXE copied")
    else:
        print("❌ EXE not found")
        return False
    print("✅ .env embedded in EXE (not copied separately)")
    bat_content = f"""@echo off
chcp 65001 >nul
title {APP_NAME} (WebView)
echo ========================================
echo    {APP_NAME} - Desktop App
echo ========================================
echo.
echo Starting application...
echo Please wait 5-10 seconds...
echo.
echo Note: Windows may show "Unknown Publisher" warning.
echo       This is normal for self-signed applications.
echo       Click "More info" -> "Run anyway" to continue.
echo.
{EXE_NAME}
echo.
echo Application started!
echo Window should open automatically.
pause
"""
    bat_path = os.path.join(package_dir, "Start.bat")
    with open(bat_path, "w", encoding="utf-8") as f:
        f.write(bat_content)
    print("✅ Start.bat created")
    readme_content = f"""# Rift Talk — Desktop Application (RU)

## Установка
1. Распакуйте все файлы в одну папку
2. Запустите **Start.bat** или **{EXE_NAME}**

## Примечание по безопасности
- Приложение подписано **самоподписанным сертификатом**
- Windows может показать предупреждение **"Unknown Publisher"**
- Это **нормально** для self-signed приложений
- Нажмите **"Подробнее" → "Выполнить в любом случае"**

## Возможности
- ✅ Встроенный интерфейс (браузер не нужен)
- ✅ Подписанный EXE (self-signed)
- ✅ Нет консольного окна
- ✅ Автоматический запуск сервера
- ✅ Автоматическое подключение к голосовым каналам команды

## Первый запуск
1. Примите предупреждение безопасности, если оно появилось
2. Откроется окно приложения с интерфейсом
3. Нажмите **"Привязать Discord"** и завершите авторизацию
4. Запустите **League of Legends** (League Client должен быть открыт)
5. Заходите в матч — **в момент начала игры** приложение автоматически закинет вас в голосовой канал вашей команды (если тиммейты тоже используют приложение)

## Как это работает
- На старте матча создаются временные голосовые каналы для **Blue/Red**
- Участникам выдаются роли/доступы и выполняется подключение к каналу команды
- После окончания матча:
  - пользователи удаляются из временных каналов
  - роли/доступы снимаются
  - временные каналы удаляются

## Важно
- Приложение должно быть **запущено ДО начала матча**
- Discord-аккаунт должен быть **привязан**
- Вы должны находиться на нужном Discord-сервере (где работает бот)
- Если Discord недоступен — приложение не сможет работать (strict mode)

## Troubleshooting
- Если окно не открывается: проверьте файл **lol_voice_chat.log**
- Предупреждение безопасности/SmartScreen: это ожидаемо → **"Подробнее" → "Выполнить в любом случае"**
- Если не закинуло в канал:
  - приложение запущено?
  - Discord запущен и вы залогинены?
  - аккаунт привязан?
  - вы на нужном сервере?
  - попробуйте перезапустить приложение и Discord
"""
    readme_path = os.path.join(package_dir, "README.txt")
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(readme_content)
    print("✅ README created")
    date_str = datetime.now().strftime("%Y%m%d_%H%M")
    zip_name = os.path.join("dist", f"{APP_NAME}_WebView_{date_str}")
    shutil.make_archive(zip_name, "zip", package_dir)
    print(f"✅ ZIP created: {zip_name}.zip")
    return True


def cleanup_temp_files():
    """Clean up temporary files."""
    for file in ["app/encrypted_env.py"]:
        if os.path.exists(file):
            os.remove(file)
            print(f"Cleaned up: {file}")


def main():
    """Main function."""
    print(f"🎮 Building {APP_NAME} with WebView")
    print("=" * 50)
    required_files = ["webview_app.py", ".env", "app", "static"]
    for f in required_files:
        if not os.path.exists(f):
            print(f"❌ Missing: {f}")
            return
    clean_build()
    create_hooks()

    print("\n🔐 Creating self-signed certificate for EXE signing...")
    if not create_self_signed_cert_for_signing():
        print("⚠️  Certificate creation failed, continuing without signing...")
        print('⚠️  EXE will show "Unknown Publisher" warning')
        signing_enabled = False
    else:
        signing_enabled = True
    if not encrypt_env_file():
        print("❌ Failed to encrypt .env file")
        cleanup_temp_files()
        return
    exe_path = build_with_pyinstaller()
    if not exe_path:
        print("❌ Build failed")
        cleanup_temp_files()
        return
    if signing_enabled:
        print("\n📝 Signing EXE file...")
        if not sign_exe_file(exe_path):
            print("⚠️  EXE signing failed, continuing without signature...")
            print("⚠️  Windows will show stronger security warning")
        else:
            print("✅ EXE signed successfully")
    else:
        print("⚠️  Skipping EXE signing (no certificate available)")
    if not create_package(exe_path):
        print("⚠️  Package creation error")
    cleanup_temp_files()
    print("\n✅ Build completed!")
    print("\n📁 Results in dist/:")
    for item in os.listdir("dist"):
        path = os.path.join("dist", item)
        if os.path.isfile(path):
            size = os.path.getsize(path) / (1024 * 1024)
            print(f"  📄 {item} ({size:.1f} MB)")
        else:
            print(f"  📁 {item}")
    print(f"\n🚀 For testing: dist/{PACKAGE_DIR_NAME}/Start.bat")
    print("🔒 .env file is encrypted and embedded in EXE")
    if signing_enabled:
        print("🔐 EXE is signed with self-signed certificate")
        print('⚠️  Windows will show "Unknown Publisher" warning')
        print("📋 Certificate files in signing_certs/ folder")
        print(f"📝 Install {CERT_BASENAME}.cer to 'Trusted Publishers' to reduce warnings")
    else:
        print("⚠️  EXE is NOT signed - strong security warning expected")
    print("=" * 50)


if __name__ == "__main__":
    main()
