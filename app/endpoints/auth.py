import logging
import json
import secrets
import urllib.parse

import requests
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm

from app.config import settings
from app.database import redis_manager
from app.schemas import TokenResponse
from app.services.lcu_service import lcu_service
from app.utils.security import create_access_token, verify_token, get_current_user


logger = logging.getLogger(__name__)

router = APIRouter(prefix='/auth', tags=['authentication'])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl='auth/token')


@router.post('/token', response_model=TokenResponse)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends()
):
    try:
        summoner_id = None
        summoner_name = form_data.username
        # Authentication through LCU
        if not lcu_service.lcu_connector.is_connected():
            raise HTTPException(
                status_code=503,
                detail='LCU not connected. Please launch League of Legends.'
            )
        current_summoner = (
            await lcu_service.lcu_connector.get_current_summoner()
        )
        if not current_summoner:
            raise HTTPException(
                status_code=404,
                detail='No summoner data available'
            )
        summoner_id = str(current_summoner.get('summonerId'))
        summoner_name = (
            current_summoner.get('displayName') or current_summoner.get(
                'gameName', summoner_name)
        )
        # Create access token
        access_token_expires = timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
        access_token = create_access_token(
            data={'sub': summoner_id, 'name': summoner_name},
            expires_delta=access_token_expires
        )
        # Save user information
        user_key = f'user:{summoner_id}'
        redis_manager.redis.hset(user_key, mapping={
            'summoner_id': summoner_id,
            'summoner_name': summoner_name,
            'last_login': datetime.now(timezone.utc).isoformat()
        })
        redis_manager.redis.expire(user_key, 3600 * 24 * 7)
        return TokenResponse(
            access_token=access_token,
            token_type='bearer',
            summoner_id=summoner_id,
            summoner_name=summoner_name
        )
    except Exception as e:
        logger.error(f'Authentication error: {e}')
        raise HTTPException(
            status_code=500,
            detail=f'Authentication failed: {str(e)}'
        )


@router.post('/verify')
async def verify_access_token(
    token: str = Depends(oauth2_scheme)
):
    """Verify JWT token validity."""
    payload = verify_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Invalid token',
            headers={'WWW-Authenticate': 'Bearer'},
        )
    return {
        'valid': True,
        'summoner_id': payload.get('sub')
    }


@router.post('/real-auth')
async def real_authentication():
    """Endpoint for authentication with real summoner_id from LCU."""
    try:
        if not lcu_service.lcu_connector.is_connected():
            raise HTTPException(
                status_code=503,
                detail='LCU not connected. Please launch League of Legends.'
            )
        current_summoner = (
            await lcu_service.lcu_connector.get_current_summoner()
        )
        if not current_summoner:
            raise HTTPException(
                status_code=404,
                detail='No summoner data available'
            )
        summoner_id = str(current_summoner.get('summonerId'))
        summoner_name = (
            current_summoner.get('displayName') or current_summoner.get(
                'gameName', 'Unknown')
        )
        # Create access token
        access_token_expires = timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
        access_token = create_access_token(
            data={'sub': summoner_id, 'name': summoner_name},
            expires_delta=access_token_expires
        )
        # Save user information in Redis
        user_key = f'user:{summoner_id}'
        redis_manager.redis.hset(user_key, mapping={
            'summoner_id': summoner_id,
            'summoner_name': summoner_name,
            'last_login': datetime.now(timezone.utc).isoformat()
        })
        redis_manager.redis.expire(user_key, 3600 * 24 * 7)
        return TokenResponse(
            access_token=access_token,
            token_type='bearer',
            summoner_id=summoner_id,
            summoner_name=summoner_name
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f'Authentication failed: {str(e)}'
        )


@router.get('/auto-auth')
async def auto_authenticate():
    """Automatic authentication using LCU when available."""
    try:
        # Try LCU authentication first
        if lcu_service.lcu_connector.is_connected():
            current_summoner = (
                await lcu_service.lcu_connector.get_current_summoner()
            )
            if current_summoner:
                summoner_id = str(current_summoner.get('summonerId'))
                summoner_name = (
                    current_summoner.get('displayName') or current_summoner.get(
                        'gameName', 'Unknown')
                )
                access_token_expires = timedelta(
                    minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
                )
                access_token = create_access_token(
                    data={'sub': summoner_id, 'name': summoner_name},
                    expires_delta=access_token_expires
                )
                # Save user info
                user_key = f'user:{summoner_id}'
                redis_manager.redis.hset(user_key, mapping={
                    'summoner_id': summoner_id,
                    'summoner_name': summoner_name,
                    'last_login': datetime.now(timezone.utc).isoformat(),
                    'auto_authenticated': 'true'
                })
                redis_manager.redis.expire(user_key, 3600 * 24 * 7)
                return TokenResponse(
                    access_token=access_token,
                    token_type='bearer',
                    summoner_id=summoner_id,
                    summoner_name=summoner_name,
                    source='lcu_auto'
                )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f'Auto-authentication failed: {str(e)}'
        )


# Discord OAuth2 linking

def _discord_redirect_uri() -> str:
    if getattr(settings, 'DISCORD_OAUTH_REDIRECT_URI', None):
        return str(settings.DISCORD_OAUTH_REDIRECT_URI)
    ui_host = '127.0.0.1' if settings.SERVER_HOST in ('0.0.0.0', '::') else settings.SERVER_HOST
    return f'http://{ui_host}:{settings.SERVER_PORT}/api/auth/discord/callback'


def _discord_oauth_enabled() -> bool:
    return bool(getattr(settings, 'DISCORD_OAUTH_CLIENT_ID', None) and getattr(settings, 'DISCORD_OAUTH_CLIENT_SECRET', None))


@router.get('/discord/login-url')
async def discord_oauth_login_url(
    current_user: dict = Depends(get_current_user),
):
    """Return Discord OAuth2 authorization URL for the current summoner.

    Requires DISCORD_OAUTH_CLIENT_ID / DISCORD_OAUTH_CLIENT_SECRET.
    """
    if not _discord_oauth_enabled():
        raise HTTPException(
            status_code=400,
            detail='Discord OAuth is not configured. Set DISCORD_OAUTH_CLIENT_ID and DISCORD_OAUTH_CLIENT_SECRET in .env'
        )

    summoner_id = str(current_user.get('sub'))
    # Create state nonce and store mapping in Redis/Memory with TTL
    nonce = secrets.token_urlsafe(24)
    state_key = f'oauth_state:{nonce}'
    payload = {
        'summoner_id': summoner_id
    }
    ttl = int(getattr(settings, 'DISCORD_OAUTH_STATE_TTL_SECONDS', 600) or 600)
    redis_manager.redis.setex(state_key, ttl, json.dumps(payload))
    params = {
        'client_id': settings.DISCORD_OAUTH_CLIENT_ID,
        'redirect_uri': _discord_redirect_uri(),
        'response_type': 'code',
        'scope': getattr(settings, 'DISCORD_OAUTH_SCOPES', 'identify') or 'identify',
        'state': nonce,
        'prompt': 'consent',
    }
    url = 'https://discord.com/api/oauth2/authorize?' + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    return JSONResponse({'url': url, 'expires_in_seconds': ttl})


@router.get('/discord/login')
async def discord_oauth_login(
    current_user: dict = Depends(get_current_user),
):
    """Redirect to Discord OAuth2."""
    data = await discord_oauth_login_url(current_user=current_user)
    # data is a JSONResponse; get body:
    try:
        body = json.loads(data.body.decode('utf-8'))
        return RedirectResponse(url=body['url'])
    except Exception:
        raise HTTPException(status_code=500, detail='Failed to build Discord OAuth URL')


@router.get('/discord/callback')
async def discord_oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
):
    """Discord OAuth2 callback. Links discord_user_id to summoner_id stored in state."""
    if not _discord_oauth_enabled():
        return HTMLResponse('<h3>Discord OAuth is not configured on this app.</h3>', status_code=400)
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
    # One-time use
    try:
        redis_manager.redis.delete(state_key)
    except Exception:
        pass
    redirect_uri = _discord_redirect_uri()
    # Exchange code -> token
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
        # Persist link (hash format)
        user_key = f'user:{summoner_id}'
        from datetime import datetime, timezone
        now_iso = datetime.now(timezone.utc).isoformat()
        redis_manager.redis.hset(user_key, mapping={
            'discord_user_id': discord_user_id,
            'discord_username': str(username),
            'summoner_id': str(summoner_id),
            'discord_linked_at': now_iso,
            'updated_at': now_iso,
            'link_method': 'oauth2'
        })
        # Keep for 30 days (refreshable)
        redis_manager.redis.expire(user_key, 30 * 24 * 3600)
        return RedirectResponse(url='/static/oauth_success.html', status_code=302)
    except Exception as e:
        return HTMLResponse(f'<h3>OAuth error: {str(e)}</h3>', status_code=500)
