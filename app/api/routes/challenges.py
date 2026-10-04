from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.firebase_auth import AuthenticatedPlayer, get_current_player
from app.db.session import get_session
from app.schemas.challenges import ChallengeAcceptance, ChallengeCreate, ChallengeRead, MatchBrief
from app.schemas.profile import PlayerBrief
from app.services import challenges

router = APIRouter(prefix="/v1/challenges", tags=["challenges"])


@router.get("", response_model=list[ChallengeRead])
async def get_challenges(
    player: AuthenticatedPlayer = Depends(get_current_player),
    session: AsyncSession = Depends(get_session),
):
    items = await challenges.list_challenges(session, player)
    return [
        ChallengeRead(
            id=challenge.id,
            status=challenge.status,
            expires_at=challenge.expires_at,
            opponent=PlayerBrief.model_validate(sender),
        )
        for challenge, sender in items
    ]


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ChallengeRead)
async def create_challenge(
    payload: ChallengeCreate,
    player: AuthenticatedPlayer = Depends(get_current_player),
    session: AsyncSession = Depends(get_session),
):
    challenge, opponent = await challenges.create_challenge(session, player, payload.friend_code)
    return ChallengeRead(
        id=challenge.id,
        status=challenge.status,
        expires_at=challenge.expires_at,
        opponent=PlayerBrief.model_validate(opponent),
    )


@router.post("/{challenge_id}/accept", response_model=ChallengeAcceptance)
async def accept_challenge(
    challenge_id: str,
    player: AuthenticatedPlayer = Depends(get_current_player),
    session: AsyncSession = Depends(get_session),
):
    challenge, result = await challenges.accept_challenge(session, player, challenge_id)
    match, participants = result
    return ChallengeAcceptance(
        status=challenge.status,
        match=MatchBrief(
            id=match.id,
            status=match.status,
            participants=[PlayerBrief.model_validate(item) for item in participants],
        ),
    )


@router.post("/{challenge_id}/decline")
async def decline_challenge(
    challenge_id: str,
    player: AuthenticatedPlayer = Depends(get_current_player),
    session: AsyncSession = Depends(get_session),
):
    challenge, _ = await challenges.decline_challenge(session, player, challenge_id)
    return {"id": challenge.id, "status": challenge.status}
