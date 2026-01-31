import asyncio
import json
import logging
import secrets
import urllib.parse
from datetime import datetime, timezone
from typing import Any

import aiohttp
import discord as discordpy
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.config import settings
from app.constants import (
    DISCORD_LINK_TTL_SECONDS,
    DISCORD_OAUTH_HTTP_TIMEOUT_SECONDS,
    REQUEST_RETRY_BACKOFF_MAX_SECONDS,
    REQUEST_RETRY_BACKOFF_START_SECONDS,
    REQUEST_RETRY_MAX_ATTEMPTS,
)
from app.database import redis_manager
from app.services.discord_service import discord_service
from app.utils.remote_key import require_client_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/public/discord', tags=['public-discord'])


def _oauth_enabled() -> bool:
    return bool(
        settings.DISCORD_OAUTH_CLIENT_ID
        and settings.DISCORD_OAUTH_CLIENT_SECRET
    )


async def _request_with_retry(
    session: aiohttp.ClientSession,
    method: str,
    url: str,
    **kwargs,
):
    """Discord HTTP with simple retry/backoff for 429/5xx."""
    backoff = REQUEST_RETRY_BACKOFF_START_SECONDS
    for attempt in range(REQUEST_RETRY_MAX_ATTEMPTS):
        async with session.request(method, url, **kwargs) as resp:
            text = await resp.text()
            data = None
            try:
                data = await resp.json(content_type=None)
            except Exception:
                data = None
            if resp.status in (429, 500, 502, 503, 504) and attempt < 2:
                retry_after = resp.headers.get('Retry-After')
                try:
                    sleep_for = int(float(retry_after)) if retry_after else backoff
                except Exception:
                    sleep_for = backoff
                await asyncio.sleep(sleep_for)
                backoff = min(
                    backoff * 2,
                    REQUEST_RETRY_BACKOFF_MAX_SECONDS,
                )
                continue
            return resp.status, text, data


@router.get('/login-url')
async def discord_login_url(
    summoner_id: str = Query(...),
    _: Any = Depends(require_client_key),
):
    if not _oauth_enabled():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Discord OAuth is not configured on server',
        )

    nonce = secrets.token_urlsafe(24)
    state_key = f'oauth_state:{nonce}'
    ttl = int(
        getattr(settings, 'DISCORD_OAUTH_STATE_TTL_SECONDS', 600) or 600
    )
    await redis_manager.redis.setex(
        state_key,
        ttl,
        json.dumps({'summoner_id': str(summoner_id)}),
    )

    params = {
        'client_id': settings.DISCORD_OAUTH_CLIENT_ID,
        'redirect_uri': settings.discord_redirect_uri(),
        'response_type': 'code',
        'scope': settings.DISCORD_OAUTH_SCOPES or 'identify',
        'state': nonce,
        'prompt': 'consent',
    }
    url = (
        'https://discord.com/api/oauth2/authorize?'
        + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    )
    return JSONResponse({'url': url, 'expires_in_seconds': ttl})


@router.get('/callback')
async def discord_callback(code: str = Query(...), state: str = Query(...)):
    if not _oauth_enabled():
        return HTMLResponse(
            '<h3>Discord OAuth is not configured on this server.</h3>',
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    state_key = f'oauth_state:{state}'
    raw = await redis_manager.redis.get(state_key)
    if not raw:
        return HTMLResponse(
            '<h3>Invalid or expired OAuth state. Please try linking again.</h3>',
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    try:
        payload = json.loads(raw)
    except Exception:
        payload = {'summoner_id': None}
    summoner_id = payload.get('summoner_id')
    if not summoner_id:
        return HTMLResponse(
            '<h3>Could not resolve summoner context. Please retry.</h3>',
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    try:
        await redis_manager.redis.delete(state_key)
    except Exception:
        pass

    redirect_uri = settings.discord_redirect_uri()

    try:
        timeout = aiohttp.ClientTimeout(
            total=DISCORD_OAUTH_HTTP_TIMEOUT_SECONDS
        )
        async with aiohttp.ClientSession(timeout=timeout) as session:
            status_code, token_text, token_data = await _request_with_retry(
                session,
                'POST',
                'https://discord.com/api/oauth2/token',
                data={
                    'client_id': settings.DISCORD_OAUTH_CLIENT_ID,
                    'client_secret': settings.DISCORD_OAUTH_CLIENT_SECRET,
                    'grant_type': 'authorization_code',
                    'code': code,
                    'redirect_uri': redirect_uri,
                },
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
            )
            if status_code != 200:
                return HTMLResponse(
                    (
                        '<h3>Failed to obtain access token from Discord.</h3>'
                        f'<pre>{token_text}</pre>'
                    ),
                    status_code=status.HTTP_400_BAD_REQUEST
                )
            token_data = token_data or {}
            access_token = token_data.get('access_token')
            if not access_token:
                return HTMLResponse(
                    '<h3>No access token returned by Discord.</h3>',
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            status_code, me_text, me = await _request_with_retry(
                session,
                'GET',
                'https://discord.com/api/users/@me',
                headers={'Authorization': f'Bearer {access_token}'},
            )
            if status_code != 200:
                return HTMLResponse(
                    (
                        '<h3>Failed to fetch user profile from Discord.</h3>'
                        f'<pre>{me_text}</pre>'
                    ),
                    status_code=status.HTTP_400_BAD_REQUEST
                )
            me = me or {}
        discord_user_id = str(me.get('id') or '')
        username = me.get('username') or me.get('global_name') or 'DiscordUser'
        if not discord_user_id:
            return HTMLResponse(
                '<h3>Discord did not return a user id.</h3>',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        now_iso = datetime.now(timezone.utc).isoformat()
        user_key = f'user:{summoner_id}'
        await redis_manager.redis.hset(
            user_key,
            mapping={
                'discord_user_id': discord_user_id,
                'discord_username': str(username),
                'summoner_id': str(summoner_id),
                'discord_linked_at': now_iso,
                'updated_at': now_iso,
                'link_method': 'oauth2',
            },
        )
        await redis_manager.redis.expire(
            user_key,
            DISCORD_LINK_TTL_SECONDS,
        )

        # Redirect to a custom success page (served from /static)
        # so the UI/webview can show a nicer screen (and optionally auto-close).
        return RedirectResponse(url='/static/oauth_success.html')
    except Exception as e:
        return HTMLResponse(
            f'<h3>OAuth error: {str(e)}</h3>',
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@router.get('/linked-account')
async def linked_account(
    summoner_id: str = Query(...),
    _: Any = Depends(require_client_key),
):
    user_key = f'user:{summoner_id}'
    user_data = await redis_manager.redis.hgetall(user_key) or {}
    discord_user_id = user_data.get('discord_user_id')
    if not discord_user_id:
        return {
            'linked': False,
            'summoner_id': str(summoner_id),
            'discord_user_id': None,
            'discord_username': None,
        }
    return {
        'linked': True,
        'summoner_id': str(summoner_id),
        'discord_user_id': str(discord_user_id),
        'discord_username': user_data.get('discord_username'),
        'linked_at': user_data.get('discord_linked_at'),
    }


@router.get('/user-server-status/{discord_user_id}')
async def user_server_status(
    discord_user_id: str,
    _: Any = Depends(require_client_key),
):
    status = {
        'discord_user_id': discord_user_id,
        'on_server': False,
        'bot_has_permissions': False,
        'can_assign_roles': False,
        'server_invite_available': False
    }
    if not discord_service.connected or not discord_service.guild:
        return status

    # Check if user is on server
    try:
        discord_id_int = int(discord_user_id)
        member = discord_service.guild.get_member(discord_id_int)
        if not member:
            try:
                member = await discord_service.guild.fetch_member(discord_id_int)
            except discordpy.NotFound:
                status['on_server'] = False
            except discordpy.Forbidden:
                status['on_server'] = 'unknown'
        else:
            status['on_server'] = True
    except (ValueError, TypeError):
        status['on_server'] = 'invalid_id'

    # Check bot permissions
    try:
        me = discord_service.guild.me
        if me:
            perms = me.guild_permissions
            status['bot_has_permissions'] = True
            status['can_assign_roles'] = bool(perms.manage_roles)
            status['server_invite_available'] = bool(perms.create_instant_invite)
    except Exception:
        pass

    return status
