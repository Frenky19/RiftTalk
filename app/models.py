from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime


class Player(BaseModel):
    summoner_id: str
    summoner_name: str
    champion_id: int
    team_id: int


class MatchData(BaseModel):
    match_id: str
    players: List[Player]
    game_mode: str
    start_time: datetime


class VoiceRoom(BaseModel):
    room_id: str
    match_id: str
    players: List[str]  # summoner_ids
    created_at: datetime
    expires_at: datetime
    is_active: bool = True


class WebRTCConfig(BaseModel):
    ice_servers: List[Dict[str, Any]]
    room_id: str
