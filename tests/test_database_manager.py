import pytest

from tests.conftest import set_server_env


@pytest.mark.asyncio
async def test_database_manager_room_lifecycle():
    set_server_env()

    from shared.database import DatabaseManager

    db = DatabaseManager()

    room_id = 'room_test'
    match_id = 'match_test'
    room_data = {
        'room_id': room_id,
        'match_id': match_id,
        'players': '[]',
        'created_at': '2026-01-01T00:00:00Z',
        'is_active': 'true',
        'blue_team': '[]',
        'red_team': '[]',
    }

    created = await db.create_voice_room(room_id, match_id, room_data, ttl=60)
    assert created is True

    by_match = await db.get_voice_room_by_match(match_id)
    assert by_match.get('room_id') == room_id
    assert by_match.get('match_id') == match_id

    deleted = await db.delete_voice_room(match_id)
    assert deleted is True

    empty = await db.get_voice_room_by_match(match_id)
    assert empty == {}
