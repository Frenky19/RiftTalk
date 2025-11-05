from pydantic import BaseModel
from typing import List, Optional, Dict


class MatchStartRequest(BaseModel):
    match_id: str
    players: List[str]
    blue_team: Optional[List[str]] = None
    red_team: Optional[List[str]] = None


class MatchEndRequest(BaseModel):
    match_id: str


class TokenRequest(BaseModel):
    summoner_id: str
    summoner_name: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class DiscordChannelResponse(BaseModel):
    channel_id: str
    channel_name: str
    invite_url: str
    team_name: str


class VoiceRoomResponse(BaseModel):
    room_id: str
    match_id: str
    players: List[str]
    discord_channels: Optional[Dict[str, DiscordChannelResponse]] = None
    created_at: str
