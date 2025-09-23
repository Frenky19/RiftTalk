import asyncio
import aiohttp
from datetime import datetime, timezone
import logging
from app.config import settings
from app.utils.lcu_connector import LCUConnector
from app.utils.exceptions import LCUException

logger = logging.getLogger(__name__)


class LCUService:
    def __init__(self):
        self.lcu_connector = LCUConnector()
        self.session = None
        self.is_monitoring = False
        self.is_initialized = False

    async def initialize(self):
        """Initialize LCU connection - fails gracefully if not available"""
        try:
            await self.lcu_connector.connect()
            self.session = aiohttp.ClientSession(
                auth=aiohttp.BasicAuth(
                    "riot",
                    self.lcu_connector.lockfile_data["password"]
                ),
                connector=aiohttp.TCPConnector(verify_ssl=False)
            )
            self.is_initialized = True
            logger.info("✅ LCU service initialized successfully")
            return True
        except Exception as e:
            self.is_initialized = False
            logger.warning(f"⚠️ LCU not available: {e}")
            return False

    async def get_current_match(self):
        """Get current match data - returns None if LCU not available"""
        if not self.is_initialized or not self.session:
            return None
        try:
            url = f"https://127.0.0.1:{self.lcu_connector.lockfile_data['port']}/lol-gameflow/v1/session"
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return self._parse_match_data(data)
                return None
        except Exception as e:
            logger.error(f"Failed to get match data: {e}")
            return None

    def _parse_match_data(self, data):
        """Parse LCU match data into our format"""
        try:
            game_data = data.get("gameData", {})
            players = []
            # Safe extraction of player data
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
                # Check for state changes
                if current_state != previous_state:
                    if current_state:  # Game started
                        logger.info(f"🎮 Game started: {current_state}")
                        await callback("match_start", current_match)
                    elif previous_state:  # Game ended
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
