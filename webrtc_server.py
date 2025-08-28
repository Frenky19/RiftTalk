import socketio
from fastapi import FastAPI
from uvicorn import Server, Config
from redis_manager import RedisManager

sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')
app = FastAPI()
sio_app = socketio.ASGIApp(sio, app)
redis_mgr = RedisManager()


@sio.event
async def connect(sid, environ):
    print(f"Клиент подключен: {sid}")


@sio.event
async def join_room(sid, data):
    match_id = data['match_id']
    summoner_id = data['summoner_id']
    if redis_mgr.is_room_active(match_id):
        await sio.save_session(
            sid, {'match_id': match_id, 'summoner_id': summoner_id}
        )
        await sio.enter_room(sid, f"voice_{match_id}")
        await sio.emit("room_joined", {"status": "success"}, room=sid)
        print(f"Игрок {summoner_id} присоединился к комнате матча {match_id}")
    else:
        await sio.emit("error", {"message": "Room not found"}, room=sid)


@sio.event
async def webrtc_offer(sid, data):
    """Пересылка WebRTC offer другим игрокам"""
    session = await sio.get_session(sid)
    await sio.emit("webrtc_offer", {
        "sender": session['summoner_id'],
        "offer": data['offer']
    }, room=f"voice_{session['match_id']}", skip_sid=sid)


@sio.event
async def webrtc_answer(sid, data):
    """Пересылка WebRTC answer"""
    session = await sio.get_session(sid)
    await sio.emit("webrtc_answer", {
        "sender": session['summoner_id'],
        "answer": data['answer']
    }, room=f"voice_{session['match_id']}", skip_sid=sid)


@sio.event
async def ice_candidate(sid, data):
    """Пересылка ICE candidate"""
    session = await sio.get_session(sid)
    await sio.emit("ice_candidate", {
        "sender": session['summoner_id'],
        "candidate": data['candidate']
    }, room=f"voice_{session['match_id']}", skip_sid=sid)


@sio.event
async def disconnect(sid):
    session = await sio.get_session(sid)
    print(f"Клиент отключен: {session.get('summoner_id', 'unknown')}")
    await sio.leave_room(sid, f"voice_{session.get('match_id', '')}")

if __name__ == "__main__":
    server = Server(Config(sio_app, host="0.0.0.0", port=8000))
    server.run()
