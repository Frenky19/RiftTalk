import socketio
from app.services.voice_service import voice_service
from app.utils.security import verify_token

sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins="*",
    logger=True,
    engineio_logger=True
)


@sio.event
async def connect(sid, environ):
    """Handle new connection"""
    try:
        # Extract and verify token from query string
        token = environ.get('HTTP_AUTHORIZATION', '').replace('Bearer ', '')
        if not token:
            raise ConnectionRefusedError('Authentication required')
        payload = verify_token(token)
        if not payload:
            raise ConnectionRefusedError('Invalid token')
        # Store user data in session
        await sio.save_session(sid, {
            'summoner_id': payload.get('sub'),
            'summoner_name': payload.get('name')
        })
        print(f"Client connected: {sid}, summoner: {payload.get('sub')}")
    except Exception as e:
        print(f"Connection failed: {e}")
        raise ConnectionRefusedError('Authentication failed')


@sio.event
async def join_room(sid, data):
    """Join a voice room"""
    session = await sio.get_session(sid)
    summoner_id = session['summoner_id']
    room_id = data.get('room_id')
    if not room_id:
        await sio.emit('error', {'message': 'Room ID required'}, room=sid)
        return
    # Validate access
    if not voice_service.validate_player_access(room_id, summoner_id):
        await sio.emit('error', {'message': 'Access denied'}, room=sid)
        return
    # Join the room
    await sio.enter_room(sid, room_id)
    await sio.emit('room_joined', {'room_id': room_id}, room=sid)
    # Notify others
    await sio.emit('user_joined', {
        'summoner_id': summoner_id,
        'summoner_name': session['summoner_name']
    }, room=room_id, skip_sid=sid)
    print(f"User {summoner_id} joined room {room_id}")


@sio.event
async def webrtc_offer(sid, data):
    """Forward WebRTC offer to other users in room"""
    session = await sio.get_session(sid)
    room_id = data.get('room_id')
    offer = data.get('offer')
    if not room_id or not offer:
        return
    await sio.emit('webrtc_offer', {
        'offer': offer,
        'sender_id': session['summoner_id']
    }, room=room_id, skip_sid=sid)


@sio.event
async def webrtc_answer(sid, data):
    """Forward WebRTC answer to other users"""
    session = await sio.get_session(sid)
    room_id = data.get('room_id')
    answer = data.get('answer')
    if not room_id or not answer:
        return
    await sio.emit('webrtc_answer', {
        'answer': answer,
        'sender_id': session['summoner_id']
    }, room=room_id, skip_sid=sid)


@sio.event
async def ice_candidate(sid, data):
    """Forward ICE candidate to other users"""
    session = await sio.get_session(sid)
    room_id = data.get('room_id')
    candidate = data.get('candidate')
    if not room_id or not candidate:
        return
    await sio.emit('ice_candidate', {
        'candidate': candidate,
        'sender_id': session['summoner_id']
    }, room=room_id, skip_sid=sid)


@sio.event
async def disconnect(sid):
    """Handle client disconnect"""
    session = await sio.get_session(sid)
    summoner_id = session.get('summoner_id', 'unknown')
    # Leave all rooms and notify users
    rooms = sio.rooms(sid)
    for room in rooms:
        if room != sid:  # Skip private room
            await sio.emit('user_left', {
                'summoner_id': summoner_id,
                'summoner_name': session.get('summoner_name', 'Unknown')
            }, room=room)
            await sio.leave_room(sid, room)
    print(f"Client disconnected: {sid}, summoner: {summoner_id}")
