import asyncio
import logging
from datetime import datetime, timedelta, timezone

from app.config import settings
from app.services.discord_service import discord_service
from app.services.voice_service import voice_service

logger = logging.getLogger(__name__)


class CleanupService:
    """Service for automatic cleanup of stale match resources.

    Goals:
    - Prevent channels/roles from accumulating if matches end abnormally (InProgress -> None, crash, etc.)
    - Work even when REDIS_URL=memory:// (app restarts), via Discord orphan GC.
    """

    def __init__(self):
        self.is_running = False
        self.cleanup_task = None
        self.cleanup_interval = int(getattr(settings, 'CLEANUP_INTERVAL_SECONDS', 60))
        self._last_discord_gc = datetime.min.replace(tzinfo=timezone.utc)

    async def start_cleanup_service(self):
        if self.is_running:
            return
        self.is_running = True
        logger.info('Starting automatic cleanup service...')
        self.cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop_cleanup_service(self):
        self.is_running = False
        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass
        logger.info('Automatic cleanup service stopped')

    async def _cleanup_loop(self):
        while self.is_running:
            try:
                await self._cleanup_rooms()
                await self._discord_orphan_gc_tick()
                await asyncio.sleep(self.cleanup_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f'Cleanup loop error: {e}')
                await asyncio.sleep(60)

    async def _cleanup_rooms(self):
        """Cleanup rooms based on age and activity."""
        try:
            current_time = datetime.now(timezone.utc)
            # Iterate over all room:* keys (works for both real Redis and memory://)
            room_keys = []
            try:
                for key in voice_service.redis.redis.scan_iter():
                    if isinstance(key, bytes):
                        key = key.decode('utf-8', errors='ignore')
                    if str(key).startswith('room:'):
                        room_keys.append(str(key))
            except Exception:
                # Fallback: DatabaseManager helper
                room_keys = [f"room:{r.get('room_id')}" for r in voice_service.redis.get_all_active_rooms() if r.get('room_id')]
            logger.info(f'Cleanup service checking {len(room_keys)} rooms')
            for key in room_keys:
                try:
                    room_id = key.split('room:', 1)[-1]
                    room_data = voice_service.redis.get_voice_room(room_id)
                    if not room_data:
                        continue
                    match_id = room_data.get('match_id')
                    if not match_id:
                        continue
                    created_at_str = room_data.get('created_at')
                    if not created_at_str:
                        continue
                    try:
                        created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                    except Exception:
                        continue
                    room_age = current_time - created_at
                    # 1) Hard safety timeout
                    if room_age > timedelta(hours=2):
                        logger.info(f'Cleaning up room for match {match_id} (hard timeout, age={room_age})')
                        await voice_service.close_voice_room(match_id)
                        continue
                    # 2) Early-leave / crash path: room explicitly marked as closing candidate
                    closing_at_str = room_data.get('closing_requested_at')
                    grace = int(getattr(settings, 'CLEANUP_INACTIVE_GRACE_SECONDS', 120))
                    stale_hours = int(getattr(settings, 'CLEANUP_STALE_EMPTY_ROOM_HOURS', 6))

                    async def _is_inactive() -> bool:
                        if not voice_service.discord_enabled:
                            return True
                        return not await discord_service.match_has_active_players(match_id)
                    if closing_at_str:
                        try:
                            closing_at = datetime.fromisoformat(closing_at_str.replace('Z', '+00:00'))
                        except Exception:
                            closing_at = created_at
                        if (current_time - closing_at).total_seconds() >= grace:
                            if await _is_inactive():
                                logger.info(
                                    f'Cleaning up room for match {match_id} '
                                    f'(marked closing, inactive for >= {grace}s)'
                                )
                                await voice_service.close_voice_room(match_id)
                                continue
                    # 3) Orphan safety: if room is old AND nobody is active, delete
                    if room_age >= timedelta(hours=stale_hours):
                        if await _is_inactive():
                            logger.info(
                                f'Cleaning up room for match {match_id} '
                                f'(stale+inactive, age={room_age})'
                            )
                            await voice_service.close_voice_room(match_id)
                except Exception as e:
                    logger.error(f'Error checking room {key}: {e}')
                    continue
        except Exception as e:
            logger.error(f'Cleanup rooms error: {e}')

    async def _discord_orphan_gc_tick(self):
        """Garbage-collect orphan channels/roles in Discord when using memory:// or after crashes."""
        try:
            if not getattr(settings, 'DISCORD_GC_ON_STARTUP', True):
                return
            if not discord_service.connected:
                return
            now = datetime.now(timezone.utc)
            # run at most every 30 minutes
            if (now - self._last_discord_gc) < timedelta(minutes=30):
                return
            self._last_discord_gc = now
            await discord_service.garbage_collect_orphaned_matches(
                max_age_hours=int(getattr(settings, 'DISCORD_GC_STALE_HOURS', 6)),
                min_age_minutes=int(getattr(settings, 'DISCORD_GC_MIN_AGE_MINUTES', 10)),
            )
        except Exception as e:
            logger.debug(f'Discord orphan GC tick failed: {e}')


cleanup_service = CleanupService()
