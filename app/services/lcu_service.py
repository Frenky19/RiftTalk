import asyncio
import aiohttp
from datetime import datetime, timezone
import logging
from typing import Optional, Dict, Any
from app.config import settings
from app.utils.lcu_connector import LCUConnector
from app.utils.exceptions import LCUException

logger = logging.getLogger(__name__)


class LCUService:
    """League Client Update service for game state monitoring."""

    def __init__(self):
        self.lcu_connector = LCUConnector()
        self.session: Optional[aiohttp.ClientSession] = None
        self.is_monitoring = False
        self.is_initialized = False
        self.monitoring_task: Optional[asyncio.Task] = None
        self._monitoring_lock = asyncio.Lock()

    async def initialize(self) -> bool:
        """Initialize LCU connection.

        Returns:
            True if initialized successfully, False otherwise
        """
        try:
            if self.is_initialized:
                logger.info("LCU service already initialized")
                return True
            # Try to connect to LCU, but don't fail if not available
            success = await self.lcu_connector.connect()
            if success:
                logger.info("✅ LCU service initialized successfully")
            else:
                logger.info("🔶 LCU service initialized in disconnected mode (game not running)")
            self.is_initialized = True
            return True
        except Exception as e:
            logger.warning(f"⚠️ LCU initialization completed with warnings: {e}")
            self.is_initialized = True  # Mark as initialized anyway
            return True  # Return True to continue application startup

    async def get_current_match(self) -> Optional[Dict[str, Any]]:
        """Get current match data from LCU.

        Returns:
            Parsed match data or None if no active game/error
        """
        if not self.is_initialized or not self.lcu_connector.is_connected():
            return None
        try:
            # Use the gameflow session endpoint to get current match info
            url = (
                f"https://127.0.0.1:{self.lcu_connector.lockfile_data['port']}"
                "/lol-gameflow/v1/session"
            )
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return self._parse_gameflow_session(data)
                elif response.status == 404:
                    return None
                else:
                    logger.warning(
                        f"LCU API returned status {response.status}"
                    )
                    return None
        except aiohttp.ClientError as e:
            logger.warning(f"Network error getting match data: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error getting match data: {e}")
            return None

    def _parse_match_data(self, data):
        """Parse LCU match data into our format"""
        try:
            game_data = data.get("gameData", {})
            players = []
            team_one = game_data.get("teamOne", []) or []
            team_two = game_data.get("teamTwo", []) or []
            for player in team_one + team_two:
                players.append({
                    "summoner_id": player.get("summonerId", ""),
                    "summoner_name": player.get("summonerName", ""),
                    "champion_id": player.get("championId", 0),
                    "team_id": player.get("teamId", 0)
                })
            return {
                "match_id": game_data.get("gameId", ""),
                "players": players,
                "game_mode": game_data.get("gameMode", ""),
                "start_time": datetime.now(timezone.utc)
            }
        except Exception as e:
            raise LCUException(f"Failed to parse match data: {e}")

    def _parse_gameflow_session(self, session_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse gameflow session data from LCU."""
        try:
            if not session_data:
                return None
            game_data = session_data.get('gameData')
            if not game_data:
                return None
            players = []
            team_one = game_data.get('teamOne', [])
            team_two = game_data.get('teamTwo', [])
            # Парсим игроков из команды 1 (синяя)
            for player in team_one:
                players.append({
                    "summoner_id": player.get('summonerId', ''),
                    "summoner_name": player.get('summonerName', ''),
                    "champion_id": player.get('championId', 0),
                    "team_id": 100  # Синяя команда
                })
            # Парсим игроков из команды 2 (красная)
            for player in team_two:
                players.append({
                    "summoner_id": player.get('summonerId', ''),
                    "summoner_name": player.get('summonerName', ''),
                    "champion_id": player.get('championId', 0),
                    "team_id": 200  # Красная команда
                })
            return {
                "match_id": str(game_data.get('gameId', '')),
                "players": players,
                "game_mode": game_data.get('gameMode', ''),
                "start_time": datetime.now(timezone.utc),
                "blue_team": [p['summoner_id'] for p in players if p['team_id'] == 100],
                "red_team": [p['summoner_id'] for p in players if p['team_id'] == 200]
            }
        except Exception as e:
            logger.error(f"Error parsing gameflow session: {e}")
            return None

    async def start_monitoring(self, callback):
        """Start monitoring game state changes.

        Works even if LCU not available.
        """
        if self.is_monitoring:
            return
        self.is_monitoring = True
        # If LCU not available, just log and return
        if not self.is_initialized:
            logger.info("🔧 LCU monitoring disabled (LCU not available)")
            return
        logger.info("🎮 Starting LCU game monitoring...")
        previous_state = None
        while self.is_monitoring:
            try:
                current_match = await self.get_current_match()
                current_state = current_match["match_id"] if current_match else None
                if current_state != previous_state:
                    if current_state:
                        logger.info(f"🎮 Game started: {current_state}")
                        await callback("match_start", current_match)
                    elif previous_state:
                        logger.info(f"🎮 Game ended: {previous_state}")
                        await callback(
                            "match_end", {"match_id": previous_state}
                        )
                    previous_state = current_state
                await asyncio.sleep(settings.LCU_UPDATE_INTERVAL)
            except Exception as e:
                logger.error(f"Monitoring error: {e}")
                await asyncio.sleep(settings.LCU_UPDATE_INTERVAL * 2)

    async def stop_monitoring(self):
        """Stop monitoring game state"""
        self.is_monitoring = False
        if self.session:
            await self.session.close()
        logger.info("🎮 LCU monitoring stopped")


lcu_service = LCUService()
