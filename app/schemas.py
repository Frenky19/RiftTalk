from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Dict, Any


class MatchStartRequest(BaseModel):
    """Request schema for starting a voice chat for a match."""

    match_id: str = Field(
        ...,
        min_length=1,
        description="Unique identifier for the match"
    )
    players: List[str] = Field(
        ...,
        min_items=1,
        description="List of summoner IDs participating in the match"
    )
    blue_team: Optional[List[str]] = Field(
        default=None,
        description="List of summoner IDs in the blue team"
    )
    red_team: Optional[List[str]] = Field(
        default=None,
        description="List of summoner IDs in the red team"
    )

    @field_validator('match_id')
    @classmethod
    def validate_match_id(cls, v: str) -> str:
        """Validate match ID is not empty."""
        if not v or not v.strip():
            raise ValueError('Match ID cannot be empty')
        return v.strip()

    model_config = {
        "str_strip_whitespace": True,
        "validate_assignment": True
    }


class MatchEndRequest(BaseModel):
    match_id: str


class TokenRequest(BaseModel):
    summoner_id: str
    summoner_name: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    summoner_id: Optional[str] = None
    summoner_name: Optional[str] = None


class DiscordChannelResponse(BaseModel):
    """Response schema for Discord channel information."""

    channel_id: str = Field(
        ...,
        description="Discord channel ID"
    )
    channel_name: str = Field(
        ...,
        description="Discord channel name"
    )
    invite_url: str = Field(
        ...,
        description="Discord invite URL for the channel"
    )
    team_name: str = Field(
        ...,
        description="Team name associated with the channel"
    )

    @field_validator('channel_id', 'channel_name', 'invite_url', 'team_name')
    @classmethod
    def validate_discord_fields(cls, v: str) -> str:
        """Validate Discord channel fields are not empty."""
        if not v or not v.strip():
            raise ValueError('Discord channel fields cannot be empty')
        return v.strip()

    model_config = {
        "str_strip_whitespace": True
    }


class VoiceRoomResponse(BaseModel):
    """Response schema for voice room information."""

    room_id: str = Field(
        ...,
        description="Unique identifier for the voice room"
    )
    match_id: str = Field(
        ...,
        description="Match ID associated with the voice room"
    )
    players: List[str] = Field(
        ...,
        description="List of summoner IDs in the voice room"
    )
    discord_channels: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Discord channels created for the voice room"
    )
    created_at: str = Field(
        ...,
        description="ISO format timestamp of room creation"
    )

    @field_validator('room_id', 'match_id')
    @classmethod
    def validate_ids(cls, v: str) -> str:
        """Validate room and match IDs are not empty."""
        if not v or not v.strip():
            raise ValueError('IDs cannot be empty')
        return v.strip()

    model_config = {
        "str_strip_whitespace": True
    }


class DiscordLinkRequest(BaseModel):
    """Schema for Discord account linking."""
    discord_user_id: int = Field(
        ...,
        description="Discord user ID to link"
    )


class DiscordAssignRequest(BaseModel):
    """Schema for Discord team assignment."""
    match_id: str = Field(
        ...,
        description="Match ID for team assignment"
    )
    team_name: str = Field(
        ...,
        description="Team name (Blue Team or Red Team)"
    )