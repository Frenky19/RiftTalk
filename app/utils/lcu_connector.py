import os
import aiohttp
import logging
import asyncio
from typing import Optional, Dict, Any
from app.utils.exceptions import LCUException

logger = logging.getLogger(__name__)


class LCUConnector:
    """League Client Update (LCU) API connector with enhanced Windows support."""

    def __init__(self):
        """Initialize LCU connector."""
        self.lockfile_path: Optional[str] = None
        self.lockfile_data: Optional[Dict[str, str]] = None
        self.session: Optional[aiohttp.ClientSession] = None
        self.is_connected_flag = False
        self._initialized = False
        self._connection_attempts = 0
        self.max_attempts = 10

    def _get_lockfile_path(self) -> Optional[str]:
        """Get the path to League of Legends lockfile for Windows with comprehensive search."""
        possible_paths = [
            # Windows paths
            os.path.join(os.getenv('LOCALAPPDATA', ''), "Riot Games", "Riot Client", "Config", "lockfile"),
            os.path.join(os.getenv('LOCALAPPDATA', ''), "Riot Games", "League of Legends", "Config", "lockfile"),
            # Alternative Windows paths
            os.path.join(os.getenv('USERPROFILE', ''), "AppData", "Local", "Riot Games", "Riot Client", "Config", "lockfile"),
            os.path.join(os.getenv('USERPROFILE', ''), "AppData", "Local", "Riot Games", "League of Legends", "Config", "lockfile"),
            # Docker paths (монтированные из Windows)
            "/host_riot_games/Riot Client/Config/lockfile",
            "/host_riot_games/League of Legends/Config/lockfile",
            # Fallback paths
            "C:/Riot Games/League of Legends/Config/lockfile",
            "D:/Riot Games/League of Legends/Config/lockfile",
        ]
        
        logger.info("🔍 Searching for LCU lockfile...")
        for path in possible_paths:
            try:
                if os.path.exists(path):
                    logger.info(f"✅ Found lockfile at: {path}")
                    return path
                else:
                    logger.debug(f"❌ Lockfile not found at: {path}")
            except Exception as e:
                logger.debug(f"⚠️ Error checking path {path}: {e}")
                continue
                
        logger.info("🔍 League client lockfile not found (game not running)")
        return None

    def is_connected(self) -> bool:
        """Check if connected to LCU API."""
        return self.is_connected_flag and self.session is not None

    async def connect(self) -> bool:
        """Connect to League Client UX API with retry logic."""
        if self._connection_attempts >= self.max_attempts:
            logger.warning("🔶 Max connection attempts reached")
            return False

        self._connection_attempts += 1
        
        try:
            self.lockfile_path = self._get_lockfile_path()
            if not self.lockfile_path:
                logger.info("🎮 League client not running - LCU connector will remain disconnected")
                return False
                
            # Read lockfile
            with open(self.lockfile_path, 'r', encoding='utf-8') as f:
                lockfile_content = f.read().strip()
                parts = lockfile_content.split(':')
                if len(parts) < 5:
                    raise LCUException("Invalid lockfile format")
                self.lockfile_data = {
                    "process_name": parts[0],
                    "pid": parts[1],
                    "port": parts[2],
                    "password": parts[3],
                    "protocol": parts[4]
                }
                
            logger.info(f"🔑 Found LCU lockfile on port {self.lockfile_data['port']}")
            
            # Create session with proper SSL handling for Windows
            self.session = aiohttp.ClientSession(
                auth=aiohttp.BasicAuth('riot', self.lockfile_data['password']),
                connector=aiohttp.TCPConnector(verify_ssl=False),
                headers={
                    'Content-Type': 'application/json',
                    'User-Agent': 'LoLVoiceChat/1.0.0'
                },
                timeout=aiohttp.ClientTimeout(total=15)
            )

            # Test connection with multiple endpoints
            test_endpoints = [
                "/lol-summoner/v1/current-summoner",
                "/lol-gameflow/v1/gameflow-phase",
                "/lol-chat/v1/me"
            ]
            
            for endpoint in test_endpoints:
                test_url = (
                    f"{self.lockfile_data['protocol']}://"
                    f"127.0.0.1:{self.lockfile_data['port']}{endpoint}"
                )
                
                try:
                    async with self.session.get(test_url) as response:
                        if response.status == 200:
                            self.is_connected_flag = True
                            self._initialized = True
                            self._connection_attempts = 0  # Reset counter on success
                            logger.info(f"✅ Successfully connected to LCU API via {endpoint}")
                            
                            # Get current summoner info for logging
                            if endpoint == "/lol-summoner/v1/current-summoner":
                                summoner_data = await response.json()
                                logger.info(f"👤 Connected as: {summoner_data.get('displayName', 'Unknown')}")
                            
                            return True
                except Exception as e:
                    logger.debug(f"⚠️ Test failed for {endpoint}: {e}")
                    continue
                    
            # If all tests failed
            raise LCUException("All connection tests failed")
                    
        except LCUException as e:
            logger.warning(f"❌ LCU connection failed (attempt {self._connection_attempts}): {e}")
            await self._cleanup()
            return False
        except Exception as e:
            logger.warning(f"❌ Unexpected error during LCU connection: {e}")
            await self._cleanup()
            return False

    async def _cleanup(self):
        """Cleanup resources."""
        if self.session:
            await self.session.close()
            self.session = None
        self.is_connected_flag = False
        self.lockfile_data = None

    async def disconnect(self):
        """Disconnect from LCU API."""
        await self._cleanup()
        logger.info("🔌 Disconnected from LCU API")

    async def make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Any] = None
    ) -> Any:
        """Make request to LCU API with enhanced error handling."""
        if not self.is_connected():
            # Try to reconnect
            logger.info("🔄 Attempting to reconnect to LCU...")
            if not await self.connect():
                raise LCUException("Not connected to LCU and reconnection failed")
            
        url = (
            f"{self.lockfile_data['protocol']}://"
            f"127.0.0.1:{self.lockfile_data['port']}{endpoint}"
        )
        
        try:
            async with self.session.request(method, url, json=data) as response:
                if response.status == 200:
                    return await response.json()
                elif response.status == 204:
                    return None
                elif response.status == 404:
                    logger.debug(f"🔍 LCU endpoint not found: {endpoint}")
                    return None
                else:
                    error_text = await response.text()
                    logger.warning(f"⚠️ LCU API error {response.status} for {endpoint}: {error_text}")
                    
                    # Handle common errors
                    if response.status == 403:
                        raise LCUException("Access forbidden - check client permissions")
                    elif response.status == 401:
                        raise LCUException("Authentication failed")
                    else:
                        raise LCUException(f"LCU API error: {response.status} - {error_text}")
                    
        except aiohttp.ClientError as e:
            logger.error(f"🌐 Network error during LCU request to {endpoint}: {e}")
            # Mark as disconnected to trigger reconnection
            self.is_connected_flag = False
            raise LCUException(f"Request to LCU API failed: {str(e)}")
        except Exception as e:
            logger.error(f"❌ Unexpected error during LCU request to {endpoint}: {e}")
            raise LCUException(f"Request to LCU API failed: {str(e)}")

    # Enhanced API methods
    async def get_current_summoner(self) -> Optional[Dict[str, Any]]:
        """Get information about current summoner."""
        try:
            return await self.make_request("GET", "/lol-summoner/v1/current-summoner")
        except LCUException:
            return None

    async def get_game_flow_phase(self) -> Optional[str]:
        """Get current game flow phase."""
        try:
            phase_data = await self.make_request("GET", "/lol-gameflow/v1/gameflow-phase")
            return phase_data if isinstance(phase_data, str) else None
        except LCUException:
            return None

    async def get_chat_me(self) -> Optional[Dict[str, Any]]:
        """Get information about current user in chat."""
        try:
            return await self.make_request("GET", "/lol-chat/v1/me")
        except LCUException:
            return None

    async def get_current_session(self) -> Optional[Dict[str, Any]]:
        """Get current game session with detailed match information."""
        try:
            return await self.make_request("GET", "/lol-gameflow/v1/session")
        except LCUException:
            return None

    async def get_live_client_data(self) -> Optional[Dict[str, Any]]:
        """Get live client data for in-game information."""
        try:
            return await self.make_request("GET", "/liveclientdata/allgamedata")
        except LCUException:
            return None

    async def get_teams(self) -> Optional[Dict[str, Any]]:
        """Get team information from current game."""
        try:
            session = await self.get_current_session()
            if not session:
                return None
                
            game_data = session.get('gameData')
            if not game_data:
                return None
                
            return {
                'blue_team': game_data.get('teamOne', []),
                'red_team': game_data.get('teamTwo', [])
            }
        except Exception as e:
            logger.error(f"Error getting teams: {e}")
            return None

    async def health_check(self) -> Dict[str, Any]:
        """Get LCU connector health status with detailed information."""
        status = {
            "connected": self.is_connected(),
            "lockfile_found": self.lockfile_path is not None,
            "initialized": self._initialized,
            "connection_attempts": self._connection_attempts
        }
        
        if self.is_connected():
            try:
                # Get additional info if connected
                summoner = await self.get_current_summoner()
                game_phase = await self.get_game_flow_phase()
                
                status.update({
                    "summoner_name": summoner.get('displayName') if summoner else None,
                    "game_phase": game_phase,
                    "port": self.lockfile_data.get('port') if self.lockfile_data else None
                })
            except Exception as e:
                logger.debug(f"Health check additional info failed: {e}")
                
        return status


lcu_connector = LCUConnector()