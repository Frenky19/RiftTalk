import json
import logging
import secrets
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import requests
import discord as discordpy
from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.config import settings
from app.database import redis_manager
from app.services.discord_service import discord_service
from app.services import persistent_store
from app.utils.remote_key import require_client_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/public/discord', tags=['public-discord'])


def _oauth_enabled() -> bool:
    return bool(settings.DISCORD_OAUTH_CLIENT_ID and settings.DISCORD_OAUTH_CLIENT_SECRET)


@router.get('/login-url')
async def discord_login_url(summoner_id: str = Query(...), _: Any = Depends(require_client_key)):
    if not _oauth_enabled():
        raise HTTPException(status_code=400, detail='Discord OAuth is not configured on server')

    nonce = secrets.token_urlsafe(24)
    state_key = f'oauth_state:{nonce}'
    ttl = int(getattr(settings, 'DISCORD_OAUTH_STATE_TTL_SECONDS', 600) or 600)
    redis_manager.redis.setex(state_key, ttl, json.dumps({'summoner_id': str(summoner_id)}))

    params = {
        'client_id': settings.DISCORD_OAUTH_CLIENT_ID,
        'redirect_uri': settings.discord_redirect_uri(),
        'response_type': 'code',
        'scope': settings.DISCORD_OAUTH_SCOPES or 'identify',
        'state': nonce,
        'prompt': 'consent',
    }
    url = 'https://discord.com/api/oauth2/authorize?' + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    return JSONResponse({'url': url, 'expires_in_seconds': ttl})


@router.get('/callback')
async def discord_callback(code: str = Query(...), state: str = Query(...)):
    if not _oauth_enabled():
        return HTMLResponse('<h3>Discord OAuth is not configured on this server.</h3>', status_code=400)

    state_key = f'oauth_state:{state}'
    raw = redis_manager.redis.get(state_key)
    if not raw:
        return HTMLResponse('<h3>Invalid or expired OAuth state. Please try linking again.</h3>', status_code=400)

    try:
        payload = json.loads(raw)
    except Exception:
        payload = {'summoner_id': None}
    summoner_id = payload.get('summoner_id')
    if not summoner_id:
        return HTMLResponse('<h3>Could not resolve summoner context. Please retry.</h3>', status_code=400)

    try:
        redis_manager.redis.delete(state_key)
    except Exception:
        pass

    redirect_uri = settings.discord_redirect_uri()

    try:
        token_resp = requests.post(
            'https://discord.com/api/oauth2/token',
            data={
                'client_id': settings.DISCORD_OAUTH_CLIENT_ID,
                'client_secret': settings.DISCORD_OAUTH_CLIENT_SECRET,
                'grant_type': 'authorization_code',
                'code': code,
                'redirect_uri': redirect_uri,
            },
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            timeout=10
        )
        if token_resp.status_code != 200:
            return HTMLResponse(
                f'<h3>Failed to obtain access token from Discord.</h3><pre>{token_resp.text}</pre>',
                status_code=400
            )
        token_data = token_resp.json()
        access_token = token_data.get('access_token')
        if not access_token:
            return HTMLResponse('<h3>No access token returned by Discord.</h3>', status_code=400)

        me_resp = requests.get(
            'https://discord.com/api/users/@me',
            headers={'Authorization': f'Bearer {access_token}'},
            timeout=10
        )
        if me_resp.status_code != 200:
            return HTMLResponse(
                f'<h3>Failed to fetch user profile from Discord.</h3><pre>{me_resp.text}</pre>',
                status_code=400
            )
        me = me_resp.json()
        discord_user_id = str(me.get('id') or '')
        username = me.get('username') or me.get('global_name') or 'DiscordUser'
        if not discord_user_id:
            return HTMLResponse('<h3>Discord did not return a user id.</h3>', status_code=400)

        now_iso = datetime.now(timezone.utc).isoformat()
        user_key = f'user:{summoner_id}'
        redis_manager.redis.hset(user_key, mapping={
            'discord_user_id': discord_user_id,
            'discord_username': str(username),
            'summoner_id': str(summoner_id),
            'discord_linked_at': now_iso,
            'updated_at': now_iso,
            'link_method': 'oauth2'
        })
        redis_manager.redis.expire(user_key, 30 * 24 * 3600)
        try:
            persistent_store.upsert_link(
                summoner_id=str(summoner_id),
                discord_user_id=str(discord_user_id),
                discord_username=str(username),
                linked_at=now_iso,
                link_method='oauth2'
            )
        except Exception as e:
            logger.warning(f'Failed to persist Discord link: {e}')

        # Redirect to a custom success page (served from /static)
        # so the UI/webview can show a nicer screen (and optionally auto-close).
        return RedirectResponse(url='/static/oauth_success.html')
    except Exception as e:
        return HTMLResponse(f'<h3>OAuth error: {str(e)}</h3>', status_code=500)


@router.get('/linked-account')
async def linked_account(summoner_id: str = Query(...), _: Any = Depends(require_client_key)):
    user_key = f'user:{summoner_id}'
    user_data = redis_manager.redis.hgetall(user_key) or {}
    discord_user_id = user_data.get('discord_user_id')
    if not discord_user_id:
        try:
            link = persistent_store.get_link_by_summoner(str(summoner_id))
        except Exception:
            link = None
        if not link or not link.get('discord_user_id'):
            return {
                'linked': False,
                'summoner_id': str(summoner_id),
                'discord_user_id': None,
                'discord_username': None,
            }
        discord_user_id = str(link.get('discord_user_id'))
        discord_username = link.get('discord_username')
        linked_at = link.get('linked_at') or link.get('updated_at')
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            redis_manager.redis.hset(user_key, mapping={
                'discord_user_id': discord_user_id,
                'discord_username': discord_username,
                'summoner_id': str(summoner_id),
                'discord_linked_at': linked_at or now_iso,
                'updated_at': now_iso,
                'link_method': link.get('link_method') or 'persistent_db'
            })
            redis_manager.redis.expire(user_key, 30 * 24 * 3600)
        except Exception:
            pass
        return {
            'linked': True,
            'summoner_id': str(summoner_id),
            'discord_user_id': discord_user_id,
            'discord_username': discord_username,
            'linked_at': linked_at,
        }
    return {
        'linked': True,
        'summoner_id': str(summoner_id),
        'discord_user_id': str(discord_user_id),
        'discord_username': user_data.get('discord_username'),
        'linked_at': user_data.get('discord_linked_at'),
    }


@router.get('/user-server-status/{discord_user_id}')
async def user_server_status(discord_user_id: str, _: Any = Depends(require_client_key)):
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
