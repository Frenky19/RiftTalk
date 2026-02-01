# Data Storage Overview

This document describes where RiftTalk stores data, how long it lives, and what
is considered persistent vs. ephemeral.

## 1) High-level

- Server:
  - Redis: short-lived operational state (rooms, matches, locks, user link).
- Client:
  - In-memory storage only (no persistence). Treat all client data as disposable.

## 2) Redis key space (ephemeral)

Redis keys are used for operational state and are safe to expire.

- `user:{summoner_id}`
  - Stores: summoner_id, summoner_name, discord_user_id, discord_username,
    timestamps, link method, current_match (optional).
  - TTL: 7 days (client auth) or 30 days (server OAuth link).
- `user_match:{summoner_id}`
  - Stores: match_id, room_id, created_at (and sometimes pending match info).
  - TTL: 1 hour.
- `room:{room_id}`
  - Stores: match_id, players, discord_channels, team lists, timestamps.
  - TTL: 1 hour.
- `match_room:{match_id}`
  - Stores: room_id for a match.
  - TTL: 1 hour.
- `user_discord:{discord_user_id}`
  - Stores: match_id / team info for Discord user auto-assign.
  - TTL: 1 hour.
- `oauth_state:{nonce}`
  - Stores: temporary OAuth state for Discord login.
  - TTL: DISCORD_OAUTH_STATE_TTL_SECONDS (default 10 minutes).
- `server_invite:{discord_user_id}`
  - Stores: temporary Discord invite URL.
  - TTL: 1 hour.
- `lock:*`
  - Stores: short-lived anti-spam/lock keys (match-start/room creation).
  - TTL: 10-30 seconds.

Notes:
- Redis is the source of truth for live match/room state.
- On server restart, Redis data is expected to be empty; rooms/roles are cleaned
  by Discord cleanup logic.

## 3) Secrets and safety

- Server secrets live only in `server/.env` (bot token, OAuth secret).
- Client `.env` is not a secret (client is distributed).
- Do not store secrets in Redis or in the client.

## 4) Operational guidance

- For production, run Redis on the server.
- On client machines, set `REDIS_URL=memory://` to avoid Redis connection warnings.
