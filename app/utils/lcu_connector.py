import os
import aiohttp
import logging
import asyncio
import ssl
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
        self.max_attempts = 5

    def _get_lockfile_path(self) -> Optional[str]:
        """Get the path to League of Legends lockfile for Windows."""
        possible_paths = [
            # Основные пути
            "C:/Riot Games/League of Legends/lockfile",  # Твой путь!
            os.path.join(os.getenv('LOCALAPPDATA', ''), "Riot Games", "Riot Client", "Config", "lockfile"),
            os.path.join(os.getenv('LOCALAPPDATA', ''), "Riot Games", "League of Legends", "Config", "lockfile"),
            os.path.join(os.getenv('USERPROFILE', ''), "AppData", "Local", "Riot Games", "Riot Client", "Config", "lockfile"),
            os.path.join(os.getenv('USERPROFILE', ''), "AppData", "Local", "Riot Games", "League of Legends", "Config", "lockfile"),
            # Альтернативные пути
            "C:/Riot Games/League of Legends/Config/lockfile",
            "D:/Riot Games/League of Legends/lockfile",
            "D:/Riot Games/League of Legends/Config/lockfile",
        ]
        
        logger.info("🔍 Searching for LCU lockfile...")
        for path in possible_paths:
            try:
                if os.path.exists(path):
                    logger.info(f"✅ Found lockfile at: {path}")
                    return path
            except Exception as e:
                logger.debug(f"⚠️ Error checking {path}: {e}")
                continue
                
        logger.info("🔍 League client lockfile not found")
        return None

    def _read_lockfile(self) -> bool:
        """Read and parse lockfile with validation."""
        try:
            if not self.lockfile_path or not os.path.exists(self.lockfile_path):
                return False
                
            with open(self.lockfile_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                
            parts = content.split(':')
            if len(parts) < 5:
                logger.error(f"❌ Invalid lockfile format: {content}")
                return False
                
            self.lockfile_data = {
                "process_name": parts[0],
                "pid": parts[1],
                "port": parts[2],
                "password": parts[3],
                "protocol": parts[4]
            }
            
            logger.info(f"🔑 Lockfile parsed - Port: {self.lockfile_data['port']}, PID: {self.lockfile_data['pid']}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to read lockfile: {e}")
            return False

    def is_connected(self) -> bool:
        """Check if connected to LCU API."""
        return self.is_connected_flag and self.session is not None

    async def connect(self) -> bool:
        """Connect to League Client UX API with comprehensive error handling."""
        if self._connection_attempts >= self.max_attempts:
            logger.warning("🔶 Max connection attempts reached")
            return False

        self._connection_attempts += 1
        logger.info(f"🔄 LCU connection attempt {self._connection_attempts}/{self.max_attempts}")
        
        try:
            # Get lockfile path
            self.lockfile_path = self._get_lockfile_path()
            if not self.lockfile_path:
                logger.info("🎮 League client not running")
                return False
                
            # Read lockfile
            if not self._read_lockfile():
                return False

            logger.info(f"🔧 Attempting connection to port {self.lockfile_data['port']} with protocol {self.lockfile_data['protocol']}")

            # Create SSL context
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

            # Create session
            self.session = aiohttp.ClientSession(
                auth=aiohttp.BasicAuth('riot', self.lockfile_data['password']),
                connector=aiohttp.TCPConnector(ssl=ssl_context),
                headers={
                    'Content-Type': 'application/json',
                    'User-Agent': 'LoLVoiceChat/1.0.0'
                },
                timeout=aiohttp.ClientTimeout(total=10)
            )

            # Test connection
            test_url = f"{self.lockfile_data['protocol']}://127.0.0.1:{self.lockfile_data['port']}/lol-summoner/v1/current-summoner"
            logger.info(f"🔗 Testing URL: {test_url}")
            
            async with self.session.get(test_url) as response:
                logger.info(f"📡 Response status: {response.status}")
                
                if response.status == 200:
                    self.is_connected_flag = True
                    self._initialized = True
                    self._connection_attempts = 0
                    
                    summoner_data = await response.json()
                    logger.info(f"✅ Successfully connected to LCU as: {summoner_data.get('displayName', 'Unknown')}")
                    return True
                else:
                    error_text = await response.text()
                    logger.error(f"❌ LCU returned status {response.status}: {error_text}")
                    return False
                    
        except aiohttp.ClientConnectorError as e:
            logger.error(f"🌐 Connection error: {e}")
            await self._cleanup()
            return False
        except aiohttp.ClientResponseError as e:
            logger.error(f"📡 HTTP error: {e}")
            await self._cleanup()
            return False
        except Exception as e:
            logger.error(f"❌ Unexpected error: {e}")
            await self._cleanup()
            return False

    async def _cleanup(self):
        """Cleanup resources."""
        if self.session:
            await self.session.close()
            self.session = None
        self.is_connected_flag = False

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
            if not await self.connect():
                raise LCUException("Not connected to LCU")
            
        url = f"{self.lockfile_data['protocol']}://127.0.0.1:{self.lockfile_data['port']}{endpoint}"
        
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
                    logger.warning(f"⚠️ LCU API error {response.status}: {error_text}")
                    return None
                    
        except aiohttp.ClientError as e:
            logger.error(f"🌐 Network error: {e}")
            self.is_connected_flag = False
            return None
        except Exception as e:
            logger.error(f"❌ LCU request error: {e}")
            return None

    # API methods
    async def get_current_summoner(self) -> Optional[Dict[str, Any]]:
        """Get current summoner information."""
        return await self.make_request("GET", "/lol-summoner/v1/current-summoner")

    async def get_game_flow_phase(self) -> Optional[str]:
        """Get current game flow phase."""
        return await self.make_request("GET", "/lol-gameflow/v1/gameflow-phase")

    async def get_current_session(self) -> Optional[Dict[str, Any]]:
        """Get current game session."""
        return await self.make_request("GET", "/lol-gameflow/v1/session")

    async def get_teams(self) -> Optional[Dict[str, Any]]:
        """Get team information from current game session."""
        try:
            session = await self.get_current_session()
            if not session:
                logger.debug("No active session found")
                return None
                
            logger.info(f"Session keys: {list(session.keys())}")
            
            # Different ways to extract team data based on session structure
            teams_data = None
            
            # Method 1: Check gameData
            game_data = session.get('gameData')
            if game_data:
                teams_data = {
                    'blue_team': game_data.get('teamOne', []),
                    'red_team': game_data.get('teamTwo', [])
                }
                logger.info("✅ Found teams in gameData")
            
            # Method 2: Check teams directly
            elif 'teams' in session:
                teams = session.get('teams', [])
                if len(teams) >= 2:
                    teams_data = {
                        'blue_team': teams[0].get('players', []),
                        'red_team': teams[1].get('players', [])
                    }
                    logger.info("✅ Found teams in teams array")
            
            # Method 3: Check myTeam for current team (during champ select)
            elif 'myTeam' in session:
                my_team = session.get('myTeam', [])
                their_team = session.get('theirTeam', [])
                
                if my_team or their_team:
                    teams_data = {
                        'blue_team': my_team,
                        'red_team': their_team
                    }
                    logger.info("✅ Found teams in myTeam/theirTeam")
        
            if teams_data:
                blue_count = len(teams_data['blue_team'])
                red_count = len(teams_data['red_team'])
                logger.info(f"👥 Teams found: Blue={blue_count}, Red={red_count}")
            else:
                logger.info("🔍 No team data found in current session")
                
            return teams_data
            
        except Exception as e:
            logger.error(f"❌ Error getting teams: {e}")
            return None

    async def get_live_client_data(self) -> Optional[Dict[str, Any]]:
        """Get live client data for in-game information."""
        return await self.make_request("GET", "/liveclientdata/allgamedata")

    async def health_check(self) -> Dict[str, Any]:
        """Get LCU connector health status."""
        return {
            "connected": self.is_connected(),
            "lockfile_found": self.lockfile_path is not None,
            "lockfile_data": {
                "port": self.lockfile_data.get('port') if self.lockfile_data else None,
                "pid": self.lockfile_data.get('pid') if self.lockfile_data else None
            } if self.lockfile_data else None,
            "connection_attempts": self._connection_attempts,
            "initialized": self._initialized
        }


lcu_connector = LCUConnector()