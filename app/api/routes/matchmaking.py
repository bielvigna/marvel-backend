from fastapi import APIRouter, Depends

from app.api.deps import get_matchmaking_service
from app.core.firebase_auth import AuthenticatedPlayer, get_current_player
from app.services.matchmaking import MatchmakingService

router = APIRouter(prefix="/v1/matchmaking", tags=["matchmaking"])


@router.post("/queue")
async def enqueue(
    player: AuthenticatedPlayer = Depends(get_current_player),
    matchmaking: MatchmakingService = Depends(get_matchmaking_service),
):
    return await matchmaking.enqueue(player)


@router.get("/queue")
async def queue_status(
    player: AuthenticatedPlayer = Depends(get_current_player),
    matchmaking: MatchmakingService = Depends(get_matchmaking_service),
):
    return await matchmaking.status(player)


@router.delete("/queue")
async def cancel_queue(
    player: AuthenticatedPlayer = Depends(get_current_player),
    matchmaking: MatchmakingService = Depends(get_matchmaking_service),
):
    return await matchmaking.cancel(player)
