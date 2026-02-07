import asyncio
import logging
import os
import ssl
from typing import Any, Dict, Optional
from urllib.parse import quote

import aiohttp

from app.utils.exceptions import LCUException
from app.utils.team_utils import (
    extract_teams_from_live_client_data,
    extract_teams_from_session,
)

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
        # Connection retry/backoff
        self._base_retry_delay = 1.0
        self._retry_delay = self._base_retry_delay
        self._max_retry_delay = 30.0
        self._next_retry_time = 0.0  # loop.time()
        self._last_error: Optional[str] = None
        self._last_connected_at: Optional[float] = None
        self._lockfile_signature: Optional[str] = None
        self._summoner_id_cache: Dict[str, str] = {}
        # Legacy field kept for compatibility (no longer enforced)
        self.max_attempts = 0

    def _get_lockfile_path(self) -> Optional[str]:
        """Get the path to League of Legends lockfile for Windows."""
        possible_paths = [
            # Main paths
            'C:/Riot Games/League of Legends/lockfile',
            os.path.join(
                os.getenv('LOCALAPPDATA', ''),
                'Riot Games',
                'Riot Client',
                'Config',
                'lockfile'
            ),
            os.path.join(
                os.getenv('LOCALAPPDATA', ''),
                'Riot Games',
                'League of Legends',
                'Config',
                'lockfile'
            ),
            os.path.join(
                os.getenv('USERPROFILE', ''),
                'AppData',
                'Local',
                'Riot Games',
                'Riot Client',
                'Config',
                'lockfile'
            ),
            os.path.join(
                os.getenv('USERPROFILE', ''),
                'AppData',
                'Local',
                'Riot Games',
                'League of Legends',
                'Config',
                'lockfile'
            ),
            # Alternative paths
            'C:/Riot Games/League of Legends/Config/lockfile',
            'D:/Riot Games/League of Legends/lockfile',
            'D:/Riot Games/League of Legends/Config/lockfile',
        ]
        logger.info('Searching for LCU lockfile...')
        for path in possible_paths:
            try:
                if os.path.exists(path):
                    logger.info(f'Found lockfile at: {path}')
                    return path
            except Exception as e:
                logger.debug(f'Error checking {path}: {e}')
                continue
        logger.info('League client lockfile not found')
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
                logger.error(f'Invalid lockfile format: {content}')
                return False
            self.lockfile_data = {
                'process_name': parts[0],
                'pid': parts[1],
                'port': parts[2],
                'password': parts[3],
                'protocol': parts[4]
            }
            logger.info(
                f'Lockfile parsed - Port: {self.lockfile_data["port"]}, '
                f'PID: {self.lockfile_data["pid"]}'
            )
            return True
        except Exception as e:
            logger.error(f'Failed to read lockfile: {e}')
            return False

    def is_connected(self) -> bool:
        """Check if connected to LCU API."""
        return self.is_connected_flag and self.session is not None

    async def connect(self) -> bool:
        """Connect to League Client UX API with comprehensive error handling."""
        if self.is_connected():
            return True

        loop = asyncio.get_running_loop()
        now = loop.time()

        # Respect the backoff window (prevents hammering when LoL/LCU is down)
        if now < self._next_retry_time:
            return False

        # Get lockfile path (do not treat missing lockfile as a failed attempt)
        self.lockfile_path = self._get_lockfile_path()
        if not self.lockfile_path:
            self.lockfile_data = None
            self._last_error = 'lockfile_not_found'
            # Keep retries gentle while the client is not running
            self._retry_delay = self._base_retry_delay
            self._next_retry_time = now + self._base_retry_delay
            return False

        # Read lockfile
        if not self._read_lockfile():
            self._last_error = 'lockfile_read_failed'
            self._retry_delay = self._base_retry_delay
            self._next_retry_time = now + self._base_retry_delay
            return False

        # If the lockfile changed (client restart), drop the old session
        signature = (
            f"{self.lockfile_data.get('protocol')}://"
            f"127.0.0.1:{self.lockfile_data.get('port')}"
            f"@{self.lockfile_data.get('password')}"
        )
        if self._lockfile_signature and self._lockfile_signature != signature:
            await self._cleanup()
        self._lockfile_signature = signature

        self._connection_attempts += 1
        logger.info(f'LCU connection attempt {self._connection_attempts}')

        try:
            logger.info(
                f'Attempting connection to port {self.lockfile_data["port"]} '
                f'with protocol {self.lockfile_data["protocol"]}'
            )

            # Create SSL context
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

            # Cleanup old session if any (defensive)
            if self.session:
                await self._cleanup()

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
            test_url = (
                f'{self.lockfile_data["protocol"]}://127.0.0.1:'
                f'{self.lockfile_data["port"]}/lol-summoner/v1/current-summoner'
            )
            logger.info(f'Testing URL: {test_url}')

            async with self.session.get(test_url) as response:
                logger.info(f'Response status: {response.status}')

                if response.status == 200:
                    self.is_connected_flag = True
                    self._initialized = True
                    self._connection_attempts = 0
                    self._retry_delay = self._base_retry_delay
                    self._next_retry_time = 0.0
                    self._last_error = None
                    self._last_connected_at = now

                    summoner_data = await response.json()
                    logger.info(
                        f'Successfully connected to LCU as: '
                        f'{summoner_data.get("displayName", "Unknown")}'
                    )
                    return True

                error_text = await response.text()
                logger.error(f'LCU returned status {response.status}: {error_text}')
                self._last_error = f'status_{response.status}'
                await self._cleanup()

                # Exponential backoff on real connection failures
                self._retry_delay = min(
                    self._max_retry_delay,
                    max(self._base_retry_delay, self._retry_delay * 2)
                )
                self._next_retry_time = now + self._retry_delay
                return False

        except aiohttp.ClientError as e:
            logger.error(f'Connection error: {e}')
            self._last_error = f'client_error:{type(e).__name__}'
            await self._cleanup()

            self._retry_delay = min(
                self._max_retry_delay,
                max(self._base_retry_delay, self._retry_delay * 2)
            )
            self._next_retry_time = now + self._retry_delay
            return False
        except Exception as e:
            logger.error(f'Unexpected error: {e}')
            self._last_error = f'unexpected:{type(e).__name__}'
            await self._cleanup()

            self._retry_delay = min(
                self._max_retry_delay,
                max(self._base_retry_delay, self._retry_delay * 2)
            )
            self._next_retry_time = now + self._retry_delay
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
        logger.info('Disconnected from LCU API')

    async def make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Any] = None
    ) -> Any:
        """Make request to LCU API with enhanced error handling."""
        if not self.is_connected():
            if not await self.connect():
                raise LCUException('Not connected to LCU')
        url = (
            f'{self.lockfile_data["protocol"]}://127.0.0.1:'
            f'{self.lockfile_data["port"]}{endpoint}'
        )
        try:
            async with self.session.request(method, url, json=data) as response:
                if response.status == 200:
                    return await response.json()
                elif response.status == 204:
                    return None
                elif response.status == 404:
                    logger.debug(f'LCU endpoint not found: {endpoint}')
                    return None
                else:
                    error_text = await response.text()
                    logger.warning(
                        f'LCU API error {response.status}: {error_text}'
                    )
                    return None
        except aiohttp.ClientError as e:
            logger.error(f'Network error: {e}')
            self._last_error = f'request_error:{type(e).__name__}'
            await self._cleanup()
            loop = asyncio.get_running_loop()
            now = loop.time()
            self._retry_delay = min(
                self._max_retry_delay,
                max(self._base_retry_delay, self._retry_delay * 2)
            )
            self._next_retry_time = now + self._retry_delay
            return None
        except Exception as e:
            logger.error(f'LCU request error: {e}')
            return None

    # API methods
    async def get_current_summoner(self) -> Optional[Dict[str, Any]]:
        """Get current summoner information."""
        return await self.make_request(
            'GET',
            '/lol-summoner/v1/current-summoner'
        )

    async def get_game_flow_phase(self) -> Optional[str]:
        """Get current game flow phase."""
        return await self.make_request(
            'GET',
            '/lol-gameflow/v1/gameflow-phase'
        )

    async def get_current_session(self) -> Optional[Dict[str, Any]]:
        """Get current game session."""
        return await self.make_request(
            'GET',
            '/lol-gameflow/v1/session'
        )

    async def get_teams(self) -> Optional[Dict[str, Any]]:
        """Get team information from current game session."""
        try:
            session = await self.get_current_session()
            if not session:
                logger.debug('No active session found')
                return None
            logger.info(f'Session keys: {list(session.keys())}')
            teams_data = extract_teams_from_session(session)
            if teams_data:
                blue_count = len(teams_data.get('blue_team', []))
                red_count = len(teams_data.get('red_team', []))
                logger.info(f'Teams found: Blue={blue_count}, Red={red_count}')
                return teams_data
            logger.info('No team data found in current session')

            live_teams = await self.get_live_client_teams()
            if live_teams:
                blue_count = len(live_teams.get('blue_team', []))
                red_count = len(live_teams.get('red_team', []))
                logger.info(
                    f'Teams found via Live Client Data: '
                    f'Blue={blue_count}, Red={red_count}'
                )
                return live_teams
            return None
        except Exception as e:
            logger.error(f'Error getting teams: {e}')
            return None

    async def get_live_client_data(self) -> Optional[Dict[str, Any]]:
        """Get live client data for in-game information."""
        url = 'http://127.0.0.1:2999/liveclientdata/allgamedata'
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=3)
            ) as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        return await response.json()
                    return None
        except Exception as e:
            logger.debug('Live client data unavailable: %s', e)
            return None

    async def _get_summoner_id_by_name(self, name: str) -> Optional[str]:
        if not name:
            return None
        key = name.strip().lower()
        cached = self._summoner_id_cache.get(key)
        if cached:
            return cached

        endpoints = [
            f'/lol-summoner/v1/summoners?name={quote(name)}',
            f'/lol-summoner/v2/summoners?name={quote(name)}',
        ]
        for endpoint in endpoints:
            data = await self.make_request('GET', endpoint)
            if isinstance(data, dict):
                summoner_id = data.get('summonerId')
                if summoner_id:
                    summoner_id = str(summoner_id)
                    self._summoner_id_cache[key] = summoner_id
                    return summoner_id
        return None

    async def get_live_client_teams(self) -> Optional[Dict[str, Any]]:
        """Extract teams using Live Client Data (port 2999)."""
        live_data = await self.get_live_client_data()
        if not live_data:
            return None

        teams = extract_teams_from_live_client_data(live_data)
        if not teams:
            return None

        async def normalize(players: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
            result: list[Dict[str, Any]] = []
            for player in players:
                if not isinstance(player, dict):
                    continue
                summoner_id = (
                    player.get('summonerId')
                    or player.get('summonerID')
                    or player.get('summonerid')
                )
                summoner_name = (
                    player.get('summonerName')
                    or player.get('summonername')
                    or player.get('playerName')
                )
                if not summoner_id and summoner_name:
                    summoner_id = await self._get_summoner_id_by_name(
                        str(summoner_name)
                    )
                if summoner_id:
                    result.append({
                        'summonerId': str(summoner_id),
                        'summonerName': str(summoner_name or ''),
                    })
            return result

        blue_team = await normalize(teams.get('blue_team', []))
        red_team = await normalize(teams.get('red_team', []))
        if not blue_team and not red_team:
            return None

        return {'blue_team': blue_team, 'red_team': red_team}

    async def health_check(self) -> Dict[str, Any]:
        """Get LCU connector health status."""
        return {
            'connected': self.is_connected(),
            'lockfile_found': self.lockfile_path is not None,
            'lockfile_data': {
                'port': (
                    self.lockfile_data.get('port')
                    if self.lockfile_data else None
                ),
                'pid': (
                    self.lockfile_data.get('pid')
                    if self.lockfile_data else None
                )
            } if self.lockfile_data else None,
            'connection_attempts': self._connection_attempts,
            'retry_in_seconds': (
                max(0.0, self._next_retry_time - asyncio.get_running_loop().time())
                if self._next_retry_time else 0.0
            ),
            'last_error': self._last_error,
            'last_connected_at': self._last_connected_at,
            'initialized': self._initialized
        }


lcu_connector = LCUConnector()
