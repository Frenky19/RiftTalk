import logging
from fastapi import APIRouter, HTTPException, Depends
from app.services.discord_service import discord_service
from app.utils.security import get_current_user
from app.database import redis_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/discord", tags=["discord-integration"])


@router.post("/link-account")
async def link_discord_account(
    discord_user_id: int,
    current_user: dict = Depends(get_current_user)
):
    """Link Discord account to LoL summoner."""
    try:
        # Save Discord user ID to Redis
        user_key = f"user:{current_user['sub']}"
        redis_manager.redis.hset(user_key, "discord_user_id", str(discord_user_id))
        redis_manager.redis.expire(user_key, 604800)  # 7 days
        logger.info(f"Linked Discord account {discord_user_id} to summoner {current_user['sub']}")
        return {
            "status": "success",
            "message": "Discord account linked successfully",
            "discord_user_id": discord_user_id,
            "summoner_id": current_user['sub']
        }
    except Exception as e:
        logger.error(f"Failed to link Discord account: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to link Discord account: {str(e)}"
        )


@router.post("/assign-to-team")
async def assign_to_team(
    match_id: str,
    team_name: str,
    current_user: dict = Depends(get_current_user)
):
    """Assign Discord user to team role."""
    try:
        # Get Discord user ID from Redis
        user_key = f"user:{current_user['sub']}"
        discord_user_id = redis_manager.redis.hget(user_key, "discord_user_id")
        if not discord_user_id:
            raise HTTPException(
                status_code=400,
                detail="Discord account not linked. Please link your Discord account first using /api/discord/link-account"
            )
        # Assign to team role
        success = await discord_service.assign_player_to_team(
            int(discord_user_id),
            match_id,
            team_name
        )
        if success:
            logger.info(f"Assigned user {discord_user_id} to {team_name} in match {match_id}")
            return {
                "status": "success",
                "message": f"Assigned to {team_name} in match {match_id}",
                "discord_user_id": discord_user_id,
                "team_name": team_name,
                "match_id": match_id
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Failed to assign to team role. Make sure the match is active and channels are created."
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to assign to team: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to assign to team: {str(e)}"
        )


@router.get("/linked-account")
async def get_linked_discord_account(
    current_user: dict = Depends(get_current_user)
):
    """Get linked Discord account information."""
    try:
        user_key = f"user:{current_user['sub']}"
        discord_user_id = redis_manager.redis.hget(user_key, "discord_user_id")
        return {
            "summoner_id": current_user['sub'],
            "discord_user_id": discord_user_id,
            "linked": discord_user_id is not None
        }
    except Exception as e:
        logger.error(f"Failed to get linked account: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get linked account: {str(e)}"
        )


@router.delete("/unlink-account")
async def unlink_discord_account(
    current_user: dict = Depends(get_current_user)
):
    """Unlink Discord account from LoL summoner."""
    try:
        user_key = f"user:{current_user['sub']}"
        redis_manager.redis.hdel(user_key, "discord_user_id")
        logger.info(f"Unlinked Discord account for summoner {current_user['sub']}")
        return {
            "status": "success",
            "message": "Discord account unlinked successfully"
        }
    except Exception as e:
        logger.error(f"Failed to unlink Discord account: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to unlink Discord account: {str(e)}"
        )
