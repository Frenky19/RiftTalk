import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Callable
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
            logger.info("🔄 Initializing LCU service...")
            
            # Try to connect
            connected = await self.lcu_connector.connect()
            
            if connected:
                summoner = await self.lcu_connector.get_current_summoner()
                if summoner:
                    logger.info(f"✅ LCU connected: {summoner.get('displayName')}")
                else:
                    logger.info("✅ LCU connected")
            else:
                logger.info("🔶 LCU not connected (game may not be running)")
                
            return True
            
        except Exception as e:
            logger.warning(f"⚠️ LCU initialization warning: {e}")
            return True

    def register_event_handler(self, event_type: str, handler: Callable):
        """Register event handler."""
        self._event_handlers[event_type] = handler
        logger.info(f"✅ Registered handler: {event_type}")

    async def start_monitoring(self):
        """Start LCU monitoring."""
        if self.is_monitoring:
            return
            
        self.is_monitoring = True
        logger.info("🎮 Starting LCU monitoring...")
        
        self.monitoring_task = asyncio.create_task(self._monitoring_loop())

    async def _monitoring_loop(self):
        """Main monitoring loop."""
        while self.is_monitoring:
            try:
                # Check connection and reconnect if needed
                if not self.lcu_connector.is_connected():
                    await self.lcu_connector.connect()
                
                # Get current phase
                current_phase = await self.lcu_connector.get_game_flow_phase()
                
                # Handle phase changes
                if current_phase and current_phase != self._previous_phase:
                    await self._handle_phase_change(current_phase)
                    
                self._previous_phase = current_phase
                
            except Exception as e:
                logger.error(f"❌ Monitoring error: {e}")
                
            await asyncio.sleep(settings.LCU_UPDATE_INTERVAL)

    async def _handle_phase_change(self, new_phase: str):
        """Handle game phase changes."""
        logger.info(f"🎮 Phase change: {self._previous_phase} → {new_phase}")
        
        # Map phases to events
        phase_events = {
            "ReadyCheck": "ready_check",
            "ChampSelect": "champ_select", 
            "InProgress": "match_start",
            "EndOfGame": "match_end",
        }
        
        event_type = phase_events.get(new_phase)
        if event_type and event_type in self._event_handlers:
            try:
                await self._event_handlers[event_type]({
                    "phase": new_phase,
                    "previous_phase": self._previous_phase,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
            except Exception as e:
                logger.error(f"❌ Error handling {event_type}: {e}")

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
            "monitoring": self.is_monitoring,
            "connected": self.lcu_connector.is_connected(),
            "current_phase": self._previous_phase,
            "event_handlers": list(self._event_handlers.keys()),
            "lcu_connector": lcu_health
        }


lcu_service = LCUService()