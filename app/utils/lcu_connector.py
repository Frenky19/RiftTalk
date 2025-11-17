import os
import aiohttp
import logging
from typing import Optional, Dict, Any
from app.utils.exceptions import LCUException

logger = logging.getLogger(__name__)


class LCUConnector:
    """League Client Update (LCU) API connector."""

    def __init__(self):
        """Initialize LCU connector without immediate lockfile check."""
        self.lockfile_path: Optional[str] = None
        self.lockfile_data: Optional[Dict[str, str]] = None
        self.session: Optional[aiohttp.ClientSession] = None
        self.is_connected_flag = False
        self._initialized = False

    def _get_lockfile_path(self) -> Optional[str]:
        """Get the path to League of Legends lockfile for Windows."""
        possible_paths = [
            # Windows paths
            os.path.join(os.getenv('LOCALAPPDATA', ''), "Riot Games", "Riot Client", "Config", "lockfile"),
            os.path.join(os.getenv('LOCALAPPDATA', ''), "Riot Games", "League of Legends", "Config", "lockfile"),
            # Docker paths (монтированные из Windows)
            "/host_riot_games/Riot Client/Config/lockfile",
            "/host_riot_games/League of Legends/Config/lockfile",
        ]
        
        for path in possible_paths:
            try:
                if os.path.exists(path):
                    logger.info(f"✅ Found lockfile at: {path}")
                    return path
            except Exception:
                continue
                
        logger.debug("League client lockfile not found (game not running)")
        return None

    def is_connected(self) -> bool:
        """Check if connected to LCU API."""
        return self.is_connected_flag and self.session is not None

    async def connect(self) -> bool:
        """Connect to League Client UX API."""
        try:
            self.lockfile_path = self._get_lockfile_path()
            if not self.lockfile_path:
                logger.info("League client not running - LCU connector will remain disconnected")
                return False
                
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
                
            logger.info(f"Found LCU lockfile on port {self.lockfile_data['port']}")
            
            self.session = aiohttp.ClientSession(
                auth=aiohttp.BasicAuth('riot', self.lockfile_data['password']),
                connector=aiohttp.TCPConnector(verify_ssl=False),
                headers={'Content-Type': 'application/json'},
                timeout=aiohttp.ClientTimeout(total=10)
            )

            # Test connection
            test_url = (
                f"{self.lockfile_data['protocol']}://"
                f"127.0.0.1:{self.lockfile_data['port']}"
                "/lol-summoner/v1/current-summoner"
            )
            
            async with self.session.get(test_url) as response:
                if response.status == 200:
                    self.is_connected_flag = True
                    self._initialized = True
                    logger.info("✅ Successfully connected to LCU API")
                    return True
                else:
                    error_text = await response.text()
                    raise LCUException(f"LCU connection test failed: {response.status} - {error_text}")
                    
        except LCUException as e:
            logger.warning(f"LCU connection failed: {e}")
            await self._cleanup()
            return False
        except Exception as e:
            logger.warning(f"Unexpected error during LCU connection: {e}")
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
        logger.info("Disconnected from LCU API")

    async def make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Any] = None
    ) -> Any:
        """Make request to LCU API.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint
            data: Request data (optional)
        Returns:
            API response data
        Raises:
            LCUException: If request fails or not connected
        """
        if not self.is_connected():
            raise LCUException("Not connected to LCU")
            
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
                else:
                    error_text = await response.text()
                    logger.error(f"LCU API error {response.status}: {error_text}")
                    raise LCUException(f"LCU API error: {response.status} - {error_text}")
                    
        except aiohttp.ClientError as e:
            logger.error(f"Network error during LCU request: {e}")
            raise LCUException(f"Request to LCU API failed: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error during LCU request: {e}")
            raise LCUException(f"Request to LCU API failed: {str(e)}")

    async def get_current_summoner(self) -> Optional[Dict[str, Any]]:
        """Get information about current summoner."""
        try:
            if not self.is_connected():
                return None
            return await self.make_request("GET", "/lol-summoner/v1/current-summoner")
        except LCUException:
            return None

    async def get_game_flow_phase(self) -> Optional[str]:
        """Get current game flow phase."""
        try:
            if not self.is_connected():
                return None
            phase_data = await self.make_request("GET", "/lol-gameflow/v1/gameflow-phase")
            return phase_data if isinstance(phase_data, str) else None
        except LCUException:
            return None

    async def get_chat_me(self) -> Optional[Dict[str, Any]]:
        """Get information about current user in chat."""
        try:
            if not self.is_connected():
                return None
            return await self.make_request("GET", "/lol-chat/v1/me")
        except LCUException:
            return None

    async def get_current_match(self) -> Optional[Dict[str, Any]]:
        """Get information about current match."""
        try:
            if not self.is_connected():
                return None
            return await self.make_request("GET", "/lol-gameflow/v1/session")
        except LCUException:
            return None

    async def health_check(self) -> Dict[str, Any]:
        """Get LCU connector health status."""
        return {
            "connected": self.is_connected(),
            "lockfile_found": self.lockfile_path is not None,
            "initialized": self._initialized
        }


lcu_connector = LCUConnector()