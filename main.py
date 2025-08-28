from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from redis_manager import RedisManager
import uvicorn
import requests
from dotenv import load_dotenv
import os

load_dotenv()

app = FastAPI()
redis_mgr = RedisManager()


# Модели данных
class MatchStartRequest(BaseModel):
    match_id: str
    players: list[str]  # Список summoner ID


class MatchEndRequest(BaseModel):
    match_id: str


# Инициализация LCU API
def get_lcu_credentials():
    lockfile_path = os.path.join(
        os.getenv("LOCALAPPDATA", ""),
        R"Riot Games\Riot Client\Config\lockfile"
    )
    if not os.path.exists(lockfile_path):
        return None
    with open(lockfile_path) as f:
        data = f.read().split(':')
        return {
            "port": data[2],
            "username": "riot",
            "password": data[3],
            "protocol": data[4]
        }


# API Endpoints
@app.post("/match/start")
async def start_match(request: MatchStartRequest):
    """Создание голосовой комнаты при старте матча"""
    room_id = redis_mgr.create_voice_room(request.match_id, request.players)
    return {
        "status": "success",
        "match_id": request.match_id,
        "room_id": room_id,
        "websocket_url": f"ws://{os.getenv('SERVER_HOST', 'localhost:8000')}/socket.io/"
    }


@app.post("/match/end")
async def end_match(request: MatchEndRequest):
    """Завершение голосовой комнаты"""
    redis_mgr.delete_room(request.match_id)
    return {"status": "closed"}


@app.get("/match/{match_id}/status")
async def match_status(match_id: str):
    """Проверка статуса комнаты"""
    return {
        "active": redis_mgr.is_room_active(match_id),
        "players": redis_mgr.get_room_players(match_id) if redis_mgr.is_room_active(match_id) else []
    }


# Интеграция с League Client
@app.on_event("startup")
async def startup_event():
    creds = get_lcu_credentials()
    if creds:
        print(f"LCU API доступен на порту: {creds['port']}")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
