import logging
import os
import threading
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import psycopg2
import psycopg2.extras

from app.config import settings

logger = logging.getLogger(__name__)

_db_lock = threading.RLock()
_dsn: Optional[str] = None


def _resolve_dsn() -> str:
    dsn = os.getenv("PERSISTENT_DB_DSN")
    if not dsn:
        dsn = os.getenv("DATABASE_URL")
    if not dsn:
        dsn = os.getenv("POSTGRES_DSN")
    if not dsn:
        dsn = getattr(settings, "PERSISTENT_DB_DSN", None)
    return str(dsn).strip() if dsn else ""


def _get_dsn() -> str:
    global _dsn
    if _dsn is None:
        _dsn = _resolve_dsn()
    return _dsn or ""


def _connect():
    dsn = _get_dsn()
    if not dsn:
        return None
    return psycopg2.connect(dsn, connect_timeout=5)


def init_db() -> Optional[str]:
    """Initialize Postgres schema for persistent links."""
    dsn = _get_dsn()
    if not dsn:
        logger.warning("Persistent DB disabled (PERSISTENT_DB_DSN not set)")
        return None

    try:
        with _db_lock, _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS discord_links (
                        summoner_id TEXT PRIMARY KEY,
                        discord_user_id TEXT NOT NULL,
                        discord_username TEXT,
                        linked_at TEXT,
                        updated_at TEXT,
                        link_method TEXT
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_discord_user_id
                    ON discord_links(discord_user_id)
                    """
                )
            conn.commit()
        return dsn
    except Exception as e:
        logger.warning(f"Persistent DB init failed: {e}")
        return None


def upsert_link(
    summoner_id: str,
    discord_user_id: str,
    discord_username: Optional[str] = None,
    linked_at: Optional[str] = None,
    link_method: Optional[str] = None,
) -> bool:
    """Insert or update a summoner->discord link."""
    if not summoner_id or not discord_user_id:
        return False

    if not _get_dsn():
        return False

    now_iso = datetime.now(timezone.utc).isoformat()
    linked_at = linked_at or now_iso
    link_method = link_method or "oauth2"

    try:
        with _db_lock, _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO discord_links (
                        summoner_id,
                        discord_user_id,
                        discord_username,
                        linked_at,
                        updated_at,
                        link_method
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT(summoner_id) DO UPDATE SET
                        discord_user_id=EXCLUDED.discord_user_id,
                        discord_username=EXCLUDED.discord_username,
                        linked_at=EXCLUDED.linked_at,
                        updated_at=EXCLUDED.updated_at,
                        link_method=EXCLUDED.link_method
                    """,
                    (
                        str(summoner_id),
                        str(discord_user_id),
                        discord_username,
                        linked_at,
                        now_iso,
                        link_method,
                    ),
                )
            conn.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to upsert link: {e}")
        return False


def get_link_by_summoner(summoner_id: str) -> Optional[Dict[str, Any]]:
    """Fetch link info by summoner_id."""
    if not summoner_id:
        return None

    if not _get_dsn():
        return None

    try:
        with _db_lock, _connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT summoner_id, discord_user_id, discord_username,
                           linked_at, updated_at, link_method
                    FROM discord_links
                    WHERE summoner_id = %s
                    """,
                    (str(summoner_id),),
                )
                row = cur.fetchone()
        return dict(row) if row else None
    except Exception as e:
        logger.error(f"Failed to fetch link for summoner {summoner_id}: {e}")
        return None


def get_link_by_discord(discord_user_id: str) -> Optional[Dict[str, Any]]:
    """Fetch link info by discord_user_id."""
    if not discord_user_id:
        return None

    if not _get_dsn():
        return None

    try:
        with _db_lock, _connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT summoner_id, discord_user_id, discord_username,
                           linked_at, updated_at, link_method
                    FROM discord_links
                    WHERE discord_user_id = %s
                    """,
                    (str(discord_user_id),),
                )
                row = cur.fetchone()
        return dict(row) if row else None
    except Exception as e:
        logger.error(
            f"Failed to fetch link for discord user {discord_user_id}: {e}"
        )
        return None
