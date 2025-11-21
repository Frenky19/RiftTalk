import asyncio
import aiohttp
from datetime import datetime, timezone
import logging
from typing import Optional, Dict, Any, Callable
from app.config import settings
from app.utils.lcu_connector import LCUConnector
from app.utils.exceptions import LCUException

logger = logging.getLogger(__name__)


class LCUService:
    """League Client Update service optimized for local Windows setup."""

    def __init__(self):
        self.lcu_connector = LCUConnector()
        self.is_monitoring = False
        self.is_initialized = False
        self.monitoring_task: Optional[asyncio.Task] = None
        self._event_handlers: Dict[str, Callable] = {}
        self._previous_phase: Optional[str] = None
        self._current_match_id: Optional[str] = None

    async def initialize(self) -> bool:
        """Initialize LCU connection for Windows."""
        try:
            if self.is_initialized:
                logger.info("LCU service already initialized")
                return True
                
            logger.info("🔄 Initializing LCU service for Windows...")
            
            # Try to connect to LCU
            success = await self.lcu_connector.connect()
            if success:
                logger.info("✅ LCU service initialized successfully")
                
                # Get initial status
                summoner = await self.lcu_connector.get_current_summoner()
                if summoner:
                    logger.info(f"👤 Current summoner: {summoner.get('displayName')}")
                    
                game_phase = await self.lcu_connector.get_game_flow_phase()
                if game_phase:
                    logger.info(f"🎮 Current game phase: {game_phase}")
                    self._previous_phase = game_phase
                    
            else:
                logger.info("🔶 LCU service initialized in disconnected mode (game not running)")
                
            self.is_initialized = True
            return True
            
        except Exception as e:
            logger.warning(f"⚠️ LCU initialization completed with warnings: {e}")
            self.is_initialized = True
            return True

    def register_event_handler(self, event_type: str, handler: Callable):
        """Register event handler for specific game events."""
        self._event_handlers[event_type] = handler
        logger.info(f"✅ Registered handler for event: {event_type}")

    async def _handle_game_phase_change(self, new_phase: str):
        """Handle game phase changes with detailed logic."""
        logger.info(f"🎮 Game phase changed: {self._previous_phase} -> {new_phase}")
        
        # Map phases to events
        phase_events = {
            "ReadyCheck": "ready_check",
            "ChampSelect": "champ_select", 
            "InProgress": "match_start",
            "EndOfGame": "match_end",
            "WaitingForStats": "match_end",
            "PreEndOfGame": "match_end"
        }
        
        event_type = phase_events.get(new_phase)
        if event_type and event_type in self._event_handlers:
            try:
                # Get match data for relevant events
                match_data = None
                if event_type in ["match_start", "champ_select"]:
                    match_data = await self._get_current_match_data()
                    
                await self._event_handlers[event_type]({
                    "phase": new_phase,
                    "previous_phase": self._previous_phase,
                    "match_data": match_data,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
                
            except Exception as e:
                logger.error(f"❌ Error handling game phase {new_phase}: {e}")
        
        self._previous_phase = new_phase

    async def _get_current_match_data(self) -> Optional[Dict[str, Any]]:
        """Get comprehensive current match data from LCU."""
        try:
            session = await self.lcu_connector.get_current_session()
            if not session:
                return None
                
            game_data = session.get('gameData')
            if not game_data:
                return None
                
            # Extract match information
            match_id = str(game_data.get('gameId', ''))
            if not match_id:
                return None
                
            players = []
            blue_team = []
            red_team = []
            
            # Process team one (blue team)
            team_one = game_data.get('teamOne', [])
            for player in team_one:
                player_data = {
                    "summoner_id": player.get('summonerId', ''),
                    "summoner_name": player.get('summonerName', ''),
                    "champion_id": player.get('championId', 0),
                    "team_id": 100
                }
                players.append(player_data)
                blue_team.append(player.get('summonerId', ''))
            
            # Process team two (red team)  
            team_two = game_data.get('teamTwo', [])
            for player in team_two:
                player_data = {
                    "summoner_id": player.get('summonerId', ''),
                    "summoner_name": player.get('summonerName', ''),
                    "champion_id": player.get('championId', 0),
                    "team_id": 200
                }
                players.append(player_data)
                red_team.append(player.get('summonerId', ''))
            
            match_data = {
                "match_id": match_id,
                "players": players,
                "blue_team": blue_team,
                "red_team": red_team,
                "game_mode": game_data.get('gameMode', ''),
                "queue_id": game_data.get('queue', {}).get('id'),
                "start_time": datetime.now(timezone.utc)
            }
            
            logger.info(f"✅ Extracted match data: {match_id} with {len(players)} players")
            return match_data
            
        except Exception as e:
            logger.error(f"❌ Error extracting match data: {e}")
            return None

    async def start_monitoring(self, callback: Callable = None):
        """Start comprehensive game state monitoring."""
        if self.is_monitoring:
            logger.info("🔶 LCU monitoring already running")
            return
            
        if callback:
            self.register_event_handler("match_start", callback)
            self.register_event_handler("match_end", callback)
            self.register_event_handler("champ_select", callback)
            self.register_event_handler("ready_check", callback)
            
        self.is_monitoring = True
        logger.info("🎮 Starting LCU game monitoring for Windows...")
        
        self.monitoring_task = asyncio.create_task(self._monitoring_loop())

    async def _monitoring_loop(self):
        """Main monitoring loop optimized for Windows."""
        logger.info("🔄 Starting LCU monitoring loop...")
        
        while self.is_monitoring:
            try:
                # Try to maintain connection
                if not self.lcu_connector.is_connected():
                    await self.lcu_connector.connect()
                    if not self.lcu_connector.is_connected():
                        await asyncio.sleep(5)
                        continue
                
                # Get current game phase
                current_phase = await self.lcu_connector.get_game_flow_phase()
                
                if current_phase and current_phase != self._previous_phase:
                    await self._handle_game_phase_change(current_phase)
                
                await asyncio.sleep(settings.LCU_UPDATE_INTERVAL)
                
            except Exception as e:
                logger.error(f"❌ Monitoring loop error: {e}")
                await asyncio.sleep(settings.LCU_UPDATE_INTERVAL * 2)

    async def stop_monitoring(self):
        """Stop monitoring game state."""
        self.is_monitoring = False
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
            self.monitoring_task = None
            
        await self.lcu_connector.disconnect()
        logger.info("🎮 LCU monitoring stopped")

    async def get_detailed_status(self) -> Dict[str, Any]:
        """Get detailed LCU service status."""
        lcu_health = await self.lcu_connector.health_check()
        
        return {
            "monitoring": self.is_monitoring,
            "initialized": self.is_initialized,
            "connected": self.lcu_connector.is_connected(),
            "current_phase": self._previous_phase,
            "event_handlers": list(self._event_handlers.keys()),
            "lcu_connector": lcu_health,
            "platform": "windows"
        }


lcu_service = LCUService()