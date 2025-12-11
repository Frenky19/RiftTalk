import asyncio
import logging
from datetime import datetime, timedelta, timezone

from app.services.voice_service import voice_service


logger = logging.getLogger(__name__)


class CleanupService:
    """Service for automatic cleanup of expired voice rooms."""

    def __init__(self):
        self.is_running = False
        self.cleanup_task = None
        self.cleanup_interval = 300  # 5 minutes

    async def start_cleanup_service(self):
        """Start the automatic cleanup service."""
        if self.is_running:
            return
        self.is_running = True
        logger.info('Starting automatic cleanup service...')
        self.cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop_cleanup_service(self):
        """Stop the automatic cleanup service."""
        self.is_running = False
        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass
        logger.info('Automatic cleanup service stopped')

    async def _cleanup_loop(self):
        """Main cleanup loop."""
        while self.is_running:
            try:
                await self._cleanup_expired_rooms()
                await asyncio.sleep(self.cleanup_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f'Cleanup loop error: {e}')
                await asyncio.sleep(60)  # Wait before retrying

    async def _cleanup_expired_rooms(self):
        """Cleanup rooms that have expired."""
        try:
            active_rooms = voice_service.redis.get_all_active_rooms()
            current_time = datetime.now(timezone.utc)
            logger.info(
                f'Cleanup service checking {len(active_rooms)} active rooms'
            )
            for room in active_rooms:
                try:
                    created_at_str = room.get('created_at')
                    if not created_at_str:
                        continue
                    # Parse creation time
                    if isinstance(created_at_str, str):
                        created_at = datetime.fromisoformat(
                            created_at_str.replace('Z', '+00:00')
                        )
                    else:
                        continue
                    # Check if room is older than 2 hours (safety timeout)
                    room_age = current_time - created_at
                    if room_age > timedelta(hours=2):
                        match_id = room.get('match_id')
                        logger.info(
                            f'Cleaning up expired room for match {match_id} '
                            f'(age: {room_age})'
                        )
                        success = await voice_service.close_voice_room(match_id)
                        if success:
                            logger.info(
                                f'Successfully cleaned up expired room for '
                                f'match {match_id}'
                            )
                        else:
                            logger.warning(
                                f'Failed to clean up expired room for '
                                f'match {match_id}'
                            )
                except Exception as e:
                    logger.error(f'Error checking room {room.get("room_id")}: {e}')
                    continue
        except Exception as e:
            logger.error(f'Cleanup expired rooms error: {e}')


cleanup_service = CleanupService()
