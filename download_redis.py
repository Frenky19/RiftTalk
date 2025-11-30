import requests
import zipfile
import os
from pathlib import Path


def download_redis():
    """Скачиваем Redis для Windows"""
    # Ссылка на Redis для Windows
    redis_url = "https://github.com/microsoftarchive/redis/releases/download/win-3.2.100/Redis-x64-3.2.100.zip"
    redis_zip = "redis.zip"
    redis_dir = "redis"
    print("📥 Скачиваем Redis для Windows...")
    try:
        # Скачиваем Redis
        print("⏬ Загружаем Redis...")
        response = requests.get(redis_url, stream=True)
        response.raise_for_status()  # Проверяем успешность запроса
        with open(redis_zip, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        # Распаковываем Redis
        print("📦 Распаковываем Redis...")
        with zipfile.ZipFile(redis_zip, 'r') as zip_ref:
            zip_ref.extractall(redis_dir)
        # Перемещаем исполняемые файлы в корень папки redis
        print("🔧 Настраиваем файлы Redis...")
        for file in Path(redis_dir).rglob("*.exe"):
            if file.parent != Path(redis_dir):
                new_path = Path(redis_dir) / file.name
                file.rename(new_path)
                print(f"   Перемещен: {file.name}")
        # Очищаем - удаляем ZIP файл
        os.remove(redis_zip)
        print("✅ Redis успешно скачан и настроен")
    except Exception as e:
        print(f"❌ Ошибка при скачивании Redis: {e}")
        # Пытаемся очистить в случае ошибки
        if os.path.exists(redis_zip):
            os.remove(redis_zip)


if __name__ == "__main__":
    download_redis()
