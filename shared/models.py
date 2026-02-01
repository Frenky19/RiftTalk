from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class Player(BaseModel):
    """Represents a player in a match."""

    summoner_id: str
    summoner_name: str
    champion_id: int
    team_id: int


class MatchData(BaseModel):
    """Represents match data."""

    match_id: str
    players: List[Player]
    game_mode: str
    start_time: datetime


class VoiceRoom(BaseModel):
    """Represents a voice room for a match."""

    room_id: str
    match_id: str
    players: List[str]
    discord_channels: Optional[Dict[str, Any]] = None
    created_at: datetime
    expires_at: datetime
    is_active: bool = True
