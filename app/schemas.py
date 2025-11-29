from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


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
    """Schema for Discord account linking with flexible validation."""
    discord_user_id: str = Field(
        ...,
        description="Discord user ID to link (as string to avoid precision loss)"
    )

    @field_validator('discord_user_id')
    @classmethod
    def validate_discord_id(cls, v: Any) -> str:
        """Flexible Discord ID validation that handles various input types."""
        
        # Если это уже строка
        if isinstance(v, str):
            cleaned = v.strip()
            logger.info(f"🔍 Validating Discord ID as string: '{cleaned}'")
            
            # Удаляем все не-цифровые символы кроме минуса (для отрицательных чисел)
            digits_only = ''.join(filter(str.isdigit, cleaned))
            
            if not digits_only:
                raise ValueError('Discord ID must contain at least one digit')
                
            if len(digits_only) < 17:
                raise ValueError(f'Discord ID must be at least 17 digits, got {len(digits_only)}')
                
            if len(digits_only) > 20:
                raise ValueError(f'Discord ID must be at most 20 digits, got {len(digits_only)}')
                
            logger.info(f"✅ Validated Discord ID: {digits_only}")
            return digits_only
            
        # Если это число
        elif isinstance(v, (int, float)):
            logger.info(f"🔍 Validating Discord ID as number: {v}")
            str_value = str(int(v))  # Конвертируем в int чтобы убрать .0 у float
            
            if len(str_value) < 17:
                raise ValueError(f'Discord ID must be at least 17 digits, got {len(str_value)}')
                
            if len(str_value) > 20:
                raise ValueError(f'Discord ID must be at most 20 digits, got {len(str_value)}')
                
            logger.info(f"✅ Validated Discord ID from number: {str_value}")
            return str_value
            
        # Любой другой тип
        else:
            logger.info(f"🔍 Validating Discord ID as other type: {type(v)} = {v}")
            str_value = str(v).strip()
            digits_only = ''.join(filter(str.isdigit, str_value))
            
            if not digits_only:
                raise ValueError(f'Discord ID must contain digits, got {v}')
                
            if len(digits_only) < 17:
                raise ValueError(f'Discord ID must be at least 17 digits, got {len(digits_only)}')
                
            if len(digits_only) > 20:
                raise ValueError(f'Discord ID must be at most 20 digits, got {len(digits_only)}')
                
            logger.info(f"✅ Validated Discord ID from other type: {digits_only}")
            return digits_only

    model_config = {
        "str_strip_whitespace": True,
        "arbitrary_types_allowed": True
    }


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