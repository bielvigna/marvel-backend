from fastapi import APIRouter, Depends

from app.api.deps import get_match_service
from app.core.firebase_auth import AuthenticatedPlayer, get_current_player
from app.schemas.matches import MatchActionRequest, TeamSubmission
from app.services.matches import MatchService

router = APIRouter(prefix="/v1/matches", tags=["matches"])


@router.get("/active")
async def get_active_match(
    player: AuthenticatedPlayer = Depends(get_current_player),
    service: MatchService = Depends(get_match_service),
):
    return {"match": await service.get_active(player)}


@router.get("/{match_id}")
async def get_match(
    match_id: str,
    player: AuthenticatedPlayer = Depends(get_current_player),
    service: MatchService = Depends(get_match_service),
):
    return await service.get(match_id, player)


@router.put("/{match_id}/teams")
async def submit_team(
    match_id: str,
    body: TeamSubmission,
    player: AuthenticatedPlayer = Depends(get_current_player),
    service: MatchService = Depends(get_match_service),
):
    return await service.submit_team(match_id, player, body.character_ids)


@router.post("/{match_id}/actions")
async def submit_action(
    match_id: str,
    body: MatchActionRequest,
    player: AuthenticatedPlayer = Depends(get_current_player),
    service: MatchService = Depends(get_match_service),
):
    return await service.submit_action(match_id, player, body.model_dump(mode="json"))
