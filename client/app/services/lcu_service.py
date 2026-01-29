import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from app.config import settings
from app.utils.lcu_connector import LCUConnector


logger = logging.getLogger(__name__)


class LCUService:
    """League Client Update service with improved connection handling."""

    def __init__(self):
        self.lcu_connector = LCUConnector()
        self.is_monitoring = False
        self.monitoring_task: Optional[asyncio.Task] = None
        self._event_handlers: Dict[str, Callable] = {}
        self._previous_phase: Optional[str] = None

    async def initialize(self) -> bool:
        """Initialize LCU service with connection retry."""
        try:
            logger.info('Initializing LCU service...')
            # Try to connect
            connected = await self.lcu_connector.connect()
            if connected:
                summoner = await self.lcu_connector.get_current_summoner()
                if summoner:
                    logger.info(
                        f'LCU connected: {summoner.get("displayName")}'
                    )
                else:
                    logger.info('LCU connected')
            else:
                logger.info(
                    'LCU not connected (game may not be running)'
                )
            return True
        except Exception as e:
            logger.warning(f'LCU initialization warning: {e}')
            return True

    def register_event_handler(self, event_type: str, handler: Callable):
        """Register event handler."""
        self._event_handlers[event_type] = handler
        logger.info(f'Registered handler: {event_type}')

    async def start_monitoring(self):
        """Start LCU monitoring."""
        if self.is_monitoring:
            return
        self.is_monitoring = True
        logger.info('Starting LCU monitoring...')
        self.monitoring_task = asyncio.create_task(self._monitoring_loop())

    async def _monitoring_loop(self):
        """Main monitoring loop."""
        while self.is_monitoring:
            try:
                # Check connection and reconnect if needed
                if not self.lcu_connector.is_connected():
                    await self.lcu_connector.connect()
                    # If still not connected, wait for next tick
                    if not self.lcu_connector.is_connected():
                        # If we were previously in a known phase and the client vanished,
                        # emit a synthetic "None" phase once so the app can treat it as a leave/disconnect.
                        if self._previous_phase not in (None, 'None'):
                            try:
                                await self._handle_phase_change('None')
                            finally:
                                self._previous_phase = 'None'
                        await asyncio.sleep(settings.LCU_UPDATE_INTERVAL)
                        continue
                # Get current phase
                current_phase = await self.lcu_connector.get_game_flow_phase()
                # Some connector failures may surface as None instead of the string "None".
                # Normalize so the phase change logic can still fire.
                if current_phase is None:
                    current_phase = 'None'
                # Handle phase changes
                if current_phase and current_phase != self._previous_phase:
                    await self._handle_phase_change(current_phase)
                self._previous_phase = current_phase
            except Exception as e:
                logger.error(f'Monitoring error: {e}')
            await asyncio.sleep(settings.LCU_UPDATE_INTERVAL)

    async def _handle_phase_change(self, new_phase: str):
        """Handle game phase changes."""
        logger.info(
            f'Phase change: {self._previous_phase} -> {new_phase}'
        )
        # Map phases to events
        phase_events = {
            'ReadyCheck': 'ready_check',
            'ChampSelect': 'champ_select',
            'InProgress': 'match_start',
            'EndOfGame': 'match_end',
            'None': 'phase_none',
        }
        event_type = phase_events.get(new_phase)
        if event_type and event_type in self._event_handlers:
            try:
                event_data = {
                    'phase': new_phase,
                    'previous_phase': self._previous_phase,
                    'timestamp': datetime.now(timezone.utc).isoformat()
                }
                # Add additional data for specific events
                if event_type == 'champ_select':
                    champ_select_data = await self.get_champ_select_data()
                    if champ_select_data:
                        event_data['champ_select_data'] = champ_select_data
                        logger.info(
                            f'Added champ select data to event: '
                            f'{len(champ_select_data.get("players", []))} players'
                        )
                    else:
                        logger.warning(
                            'No champ select data available for event'
                        )
                await self._event_handlers[event_type](event_data)
            except Exception as e:
                logger.error(f'Error handling {event_type}: {e}')

    async def stop_monitoring(self):
        """Stop LCU monitoring."""
        self.is_monitoring = False
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
        await self.lcu_connector.disconnect()

    async def get_detailed_status(self) -> Dict[str, Any]:
        """Get detailed LCU status."""
        lcu_health = await self.lcu_connector.health_check()
        return {
            'monitoring': self.is_monitoring,
            'connected': self.lcu_connector.is_connected(),
            'current_phase': self._previous_phase,
            'event_handlers': list(self._event_handlers.keys()),
            'lcu_connector': lcu_health
        }

    async def get_champ_select_data(self) -> Optional[Dict[str, Any]]:
        """Get detailed champion selection data including teams."""
        try:
            if not self.lcu_connector.is_connected():
                logger.warning('LCU not connected')
                return None
            # First try to get data from champ select specific endpoint
            champ_select_data = await self._get_champ_select_session_data()
            if champ_select_data:
                return champ_select_data
            # Fallback to general session data
            session = await self.lcu_connector.get_current_session()
            if not session:
                logger.warning('No active session')
                return None
            logger.info(f'Raw session keys: {list(session.keys())}')
            # Try different methods to extract team data
            teams_data = await self._extract_teams_from_session(session)
            if teams_data:
                # Generate match ID from session
                match_id = self._generate_match_id(session)
                # Normalize player data - extract only summonerId
                blue_team_ids = [
                    str(player.get('summonerId'))
                    for player in teams_data.get('blue_team', [])
                    if player.get('summonerId')
                ]
                red_team_ids = [
                    str(player.get('summonerId'))
                    for player in teams_data.get('red_team', [])
                    if player.get('summonerId')
                ]
                # All players from both teams
                all_players = blue_team_ids + red_team_ids
                result = {
                    'match_id': match_id,
                    'teams': {
                        'blue_team': blue_team_ids,
                        'red_team': red_team_ids
                    },
                    'players': all_players,
                    'session_data': {
                        'phase': 'ChampSelect',
                        'game_mode': session.get('gameData', {}).get('gameMode'),
                        'queue_id': (
                            session.get('gameData', {})
                            .get('queue', {})
                            .get('id')
                        )
                    },
                    'raw_teams_data': teams_data  # For debugging
                }
                logger.info(
                    f'Extracted champ select data: '
                    f'Blue={len(blue_team_ids)}, Red={len(red_team_ids)}'
                )
                logger.info(f'Blue team IDs: {blue_team_ids}')
                logger.info(f'Red team IDs: {red_team_ids}')
                return result
            logger.warning('No team data found in champ select session')
            return None
        except Exception as e:
            logger.error(f'Failed to get champ select data: {e}')
            return None

    async def _get_champ_select_session_data(self) -> Optional[Dict[str, Any]]:
        """Get champ select data from dedicated champ select endpoint."""
        try:
            # Try to get champ select specific data
            champ_select_session = await self.lcu_connector.make_request(
                'GET', '/lol-champ-select/v1/session'
            )
            if champ_select_session:
                logger.info('Found champ select session data')
                return await self._parse_champ_select_session(
                    champ_select_session
                )
            return None
        except Exception as e:
            logger.debug(f'Champ select endpoint not available: {e}')
            return None

    async def _parse_champ_select_session(
        self,
        champ_select_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Parse dedicated champ select session data."""
        try:
            blue_team = []
            red_team = []
            # Extract teams from champ select data
            if 'myTeam' in champ_select_data:
                for player in champ_select_data['myTeam']:
                    if player.get('summonerId'):
                        blue_team.append(str(player['summonerId']))
                        logger.debug(
                            f'Champ select blue team: '
                            f'{player.get("summonerName", "Unknown")} '
                            f'(ID: {player["summonerId"]})'
                        )
            # In champ select, we might not have enemy team data yet
            # But we can create rooms with just our team for now
            if blue_team:
                match_id = f'champ_select_{int(datetime.now(timezone.utc).timestamp())}'
                logger.info(
                    f'Parsed champ select data: {len(blue_team)} '
                    f'players in blue team'
                )
                return {
                    'match_id': match_id,
                    'teams': {
                        'blue_team': blue_team,
                        'red_team': red_team
                    },
                    'players': blue_team + red_team,
                    'session_data': {
                        'phase': 'ChampSelect',
                        'source': 'champ_select_endpoint'
                    }
                }
            return None
        except Exception as e:
            logger.error(f'Error parsing champ select session: {e}')
            return None

    async def _extract_teams_from_session(
        self,
        session: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Extract team data from LCU session with FIX for team swapping bug."""
        try:
            blue_team = []
            red_team = []
            logger.info('Searching for team data in session...')
            logger.info(f'Session keys: {list(session.keys())}')
            # Method 1: Check direct blue_team/red_team keys (most reliable)
            if 'blue_team' in session or 'red_team' in session:
                logger.info('Found teams in blue_team/red_team keys')
                blue_team_data = session.get('blue_team', [])
                red_team_data = session.get('red_team', [])
                logger.info(f'Raw blue_team data: {blue_team_data}')
                logger.info(f'Raw red_team data: {red_team_data}')
                # Process blue_team
                if isinstance(blue_team_data, list):
                    for player in blue_team_data:
                        if (
                            player and isinstance(
                                player, dict) and player.get('summonerId')
                        ):
                            blue_team.append({
                                'summonerId': str(player.get('summonerId')),
                                'summonerName': player.get('summonerName', 'Unknown'),
                                'championId': player.get('championId')
                            })
                            logger.info(
                                f'Blue team player: '
                                f'{player.get("summonerName", "Unknown")} '
                                f'(ID: {player["summonerId"]})'
                            )
                # Process red_team
                if isinstance(red_team_data, list):
                    for player in red_team_data:
                        if (
                            player and isinstance(
                                player, dict) and player.get('summonerId')
                        ):
                            red_team.append({
                                'summonerId': str(player.get('summonerId')),
                                'summonerName': player.get('summonerName', 'Unknown'),
                                'championId': player.get('championId')
                            })
                            logger.info(
                                f'Red team player: '
                                f'{player.get("summonerName", "Unknown")} '
                                f'(ID: {player["summonerId"]})'
                            )
            # Method 2: myTeam/theirTeam (fallback)
            elif 'myTeam' in session and 'theirTeam' in session:
                logger.info('Found teams in myTeam/theirTeam')
                for player in session['myTeam']:
                    if player.get('summonerId'):
                        blue_team.append({
                            'summonerId': str(player.get('summonerId')),
                            'summonerName': player.get('summonerName', 'Unknown'),
                            'championId': player.get('championId')
                        })
                for player in session['theirTeam']:
                    if player.get('summonerId'):
                        red_team.append({
                            'summonerId': str(player.get('summonerId')),
                            'summonerName': player.get('summonerName', 'Unknown'),
                            'championId': player.get('championId')
                        })
            # Method 3: teams array (fallback)
            elif 'teams' in session and len(session['teams']) >= 2:
                logger.info('Found teams in teams array')
                for player in session['teams'][0].get('players', []):
                    if player.get('summonerId'):
                        blue_team.append({
                            'summonerId': str(player.get('summonerId')),
                            'summonerName': player.get('summonerName', 'Unknown'),
                            'championId': player.get('championId')
                        })
                for player in session['teams'][1].get('players', []):
                    if player.get('summonerId'):
                        red_team.append({
                            'summonerId': str(player.get('summonerId')),
                            'summonerName': player.get('summonerName', 'Unknown'),
                            'championId': player.get('championId')
                        })
            # Log final teams
            logger.info(
                f'Final teams - Blue: {[p["summonerId"] for p in blue_team]}, '
                f'Red: {[p["summonerId"] for p in red_team]}'
            )
            if blue_team or red_team:
                return {
                    'blue_team': blue_team,
                    'red_team': red_team
                }
            logger.warning('No team data found in session')
            return None
        except Exception as e:
            logger.error(f'Error extracting teams from session: {e}')
            return None

    def _generate_match_id(self, session: Dict[str, Any]) -> str:
        """Generate unique match ID from session data."""
        try:
            # Try to get existing match ID
            if 'gameData' in session and session['gameData'].get('gameId'):
                return f"match_{session['gameData']['gameId']}"
            # Generate from chat room name
            if 'chatRoomName' in session:
                return f"chat_{session['chatRoomName']}"
            # Fallback to timestamp-based ID
            return f'match_{int(datetime.now(timezone.utc).timestamp())}'
        except Exception as e:
            logger.error(f'Error generating match ID: {e}')
            return f'match_{int(datetime.now(timezone.utc).timestamp())}'

    async def get_detailed_champ_select_info(self) -> Dict[str, Any]:
        """Get comprehensive champ select information for debugging."""
        try:
            session = await self.lcu_connector.get_current_session()
            if not session:
                return {'error': 'No active session'}
            champ_select_data = await self.get_champ_select_data()
            champ_select_session = await self._get_champ_select_session_data()
            # Get current summoner for reference
            current_summoner = await self.lcu_connector.get_current_summoner()
            return {
                'session_keys': list(session.keys()),
                'game_phase': await self.lcu_connector.get_game_flow_phase(),
                'champ_select_data': champ_select_data,
                'champ_select_session_data': champ_select_session,
                'current_summoner_id': (
                    current_summoner.get('summonerId')
                    if current_summoner else None
                ),
                'has_myTeam': 'myTeam' in session,
                'has_theirTeam': 'theirTeam' in session,
                'has_teams': 'teams' in session,
                'has_blue_team': 'blue_team' in session,
                'has_red_team': 'red_team' in session,
                'myTeam_count': len(session.get('myTeam', [])),
                'theirTeam_count': len(session.get('theirTeam', [])),
                'teams_count': len(session.get('teams', [])),
                'blue_team_count': len(session.get('blue_team', [])),
                'red_team_count': len(session.get('red_team', [])),
                'myTeam_sample': [
                    {
                        'summonerId': p.get('summonerId'),
                        'summonerName': p.get('summonerName')
                    }
                    for p in session.get('myTeam', [])[:2]
                ] if session.get('myTeam') else [],
                'theirTeam_sample': [
                    {
                        'summonerId': p.get('summonerId'),
                        'summonerName': p.get('summonerName')
                    }
                    for p in session.get('theirTeam', [])[:2]
                ] if session.get('theirTeam') else [],
                'blue_team_sample': [
                    {
                        'summonerId': p.get('summonerId'),
                        'summonerName': p.get('summonerName')
                    }
                    for p in session.get('blue_team', [])[:2]
                ] if session.get('blue_team') else [],
                'red_team_sample': [
                    {
                        'summonerId': p.get('summonerId'),
                        'summonerName': p.get('summonerName')
                    }
                    for p in session.get('red_team', [])[:2]
                ] if session.get('red_team') else []
            }
        except Exception as e:
            logger.error(f'Error getting detailed champ select info: {e}')
            return {'error': str(e)}


lcu_service = LCUService()
