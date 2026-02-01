from fastapi import APIRouter, Depends, HTTPException, status

from app.database import redis_manager
from app.services.lcu_service import lcu_service
from app.utils.security import get_current_user

router = APIRouter(prefix='/lcu', tags=['lcu-integration'])


@router.get('/status')
async def lcu_connection_status(
    current_user: dict = Depends(get_current_user)
):
    """Check LCU connection status with detailed information."""
    try:
        detailed_status = await lcu_service.get_detailed_status()
        return {
            'status': 'success',
            'lcu_service': detailed_status
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f'LCU connection error: {str(e)}',
        )


@router.get('/current-game')
async def get_current_game_info(
    current_user: dict = Depends(get_current_user)
):
    """Get detailed information about current game."""
    try:
        if not lcu_service.lcu_connector.is_connected():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail='LCU not connected',
            )
        session = await lcu_service.lcu_connector.get_current_session()
        if not session:
            return {'status': 'no_active_session'}
        game_phase = await lcu_service.lcu_connector.get_game_flow_phase()
        summoner = await lcu_service.lcu_connector.get_current_summoner()
        return {
            'status': 'success',
            'game_phase': game_phase,
            'summoner': summoner,
            'session_keys': list(session.keys()) if session else []
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f'Failed to get game info: {str(e)}',
        )


@router.get('/current-summoner')
async def get_current_summoner_info(
    current_user: dict = Depends(get_current_user)
):
    """Get information about current summoner."""
    try:
        if not lcu_service.lcu_connector.is_connected():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail='LCU not connected',
            )
        summoner = await lcu_service.lcu_connector.get_current_summoner()
        if not summoner:
            return {'status': 'no_summoner_info'}
        return {
            'status': 'success',
            'summoner': summoner
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f'Failed to get summoner info: {str(e)}',
        )


@router.get('/teams')
async def get_current_teams(
    current_user: dict = Depends(get_current_user)
):
    """Get team information in current game."""
    try:
        if not lcu_service.lcu_connector.is_connected():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail='LCU not connected',
            )
        teams = await lcu_service.lcu_connector.get_teams()
        if not teams:
            return {
                'status': 'no_team_data',
                'message': 'No team data available in current session',
                'note': 'Team data is usually available during champion '
                        'select or in-game'
            }
        return {
            'status': 'success',
            'teams': teams
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f'Failed to get teams: {str(e)}',
        )


@router.get('/champ-select-debug')
async def get_champ_select_debug(
    current_user: dict = Depends(get_current_user)
):
    """Debug endpoint for champ select data."""
    try:
        detailed_info = await lcu_service.get_detailed_champ_select_info()
        return {
            'status': 'success',
            'champ_select_debug': detailed_info
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f'Champ select debug failed: {str(e)}',
        )


@router.get('/session-debug')
async def get_session_debug(
    current_user: dict = Depends(get_current_user)
):
    """Debug endpoint to see raw session data."""
    try:
        if not lcu_service.lcu_connector.is_connected():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail='LCU not connected',
            )
        session = await lcu_service.lcu_connector.get_current_session()
        if not session:
            return {'status': 'no_session'}
        # Return limited session data for debugging
        debug_data = {
            'session_keys': list(session.keys()),
            'game_phase': await lcu_service.lcu_connector.get_game_flow_phase(),
            'has_gameData': 'gameData' in session,
            'has_teams': 'teams' in session,
            'has_myTeam': 'myTeam' in session,
            'gameData_keys': list(session.get('gameData', {}).keys())
            if session.get('gameData') else None
        }
        return {
            'status': 'success',
            'debug': debug_data,
            'session_sample': {k: type(v).__name__ for k, v in session.items()}
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f'Debug failed: {str(e)}',
        )


@router.post('/auto-voice')
async def toggle_auto_voice(
    enabled: bool, current_user: dict = Depends(get_current_user)
):
    """Enable/disable automatic voice room creation."""
    try:
        # Save user settings
        user_key = f'user:{current_user["sub"]}'
        await redis_manager.redis.hset(
            user_key, 'auto_voice', str(enabled).lower()
        )
        # If enabling auto-voice and there's an active game, create room
        if enabled and lcu_service.lcu_connector.is_connected():
            game_phase = await lcu_service.lcu_connector.get_game_flow_phase()
            if game_phase in ['ChampSelect', 'InProgress']:
                pass
        return {
            'status': 'success',
            'auto_voice': enabled,
            'message': f'Auto voice {"enabled" if enabled else "disabled"}'
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f'Failed to update settings: {str(e)}',
        )


@router.post('/force-reconnect')
async def force_lcu_reconnect(
    current_user: dict = Depends(get_current_user)
):
    """Force reconnect to LCU."""
    try:
        await lcu_service.lcu_connector.disconnect()
        success = await lcu_service.lcu_connector.connect()
        return {
            'status': 'success' if success else 'failed',
            'reconnected': success,
            'message': 'LCU reconnection attempted'
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f'Failed to reconnect: {str(e)}',
        )


@router.get('/debug-session-data')
async def debug_session_data(current_user: dict = Depends(get_current_user)):
    """Debug endpoint to see raw session data and team extraction."""
    try:
        if not lcu_service.lcu_connector.is_connected():
            return {'error': 'LCU not connected'}
        session = await lcu_service.lcu_connector.get_current_session()
        if not session:
            return {'error': 'No active session'}
        # Get raw session data
        raw_session = {
            'keys': list(session.keys()),
            'has_blue_team': 'blue_team' in session,
            'has_red_team': 'red_team' in session,
            'has_myTeam': 'myTeam' in session,
            'has_theirTeam': 'theirTeam' in session,
            'has_teams': 'teams' in session,
        }
        # Get teams using different methods
        teams_from_connector = await lcu_service.lcu_connector.get_teams()
        teams_from_service = await lcu_service._extract_teams_from_session(
            session)
        # Get champ select data
        champ_select_data = await lcu_service.get_champ_select_data()
        return {
            'raw_session': raw_session,
            'teams_from_connector': teams_from_connector,
            'teams_from_service': teams_from_service,
            'champ_select_data': champ_select_data,
            'session_sample': {
                'blue_team': session.get('blue_team', [])[:2]
                if isinstance(session.get('blue_team'), list)
                else session.get('blue_team'),
                'red_team': session.get('red_team', [])[:2]
                if isinstance(session.get('red_team'), list)
                else session.get('red_team'),
                'myTeam': session.get('myTeam', [])[:2]
                if isinstance(session.get('myTeam'), list)
                else session.get('myTeam'),
                'theirTeam': session.get('theirTeam', [])[:2]
                if isinstance(session.get('theirTeam'), list)
                else session.get('theirTeam'),
            }
        }
    except Exception as e:
        return {'error': str(e)}
