from pydantic import BaseModel
from typing import List, Optional


class MatchStartRequest(BaseModel):
    match_id: str
    players: List[str]


class MatchEndRequest(BaseModel):
    match_id: str


class TokenRequest(BaseModel):
    summoner_id: str
    summoner_name: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class VoiceRoomResponse(BaseModel):
    room_id: str
    match_id: str
    webrtc_config: dict
    players: List[str]
