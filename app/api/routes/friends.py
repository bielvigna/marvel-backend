from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_presence_service
from app.core.errors import GameplayError
from app.core.firebase_auth import AuthenticatedPlayer, get_current_player
from app.db.session import get_session
from app.schemas.profile import FriendRequestRead, FriendTargetRequest, PlayerBrief
from app.services import friends
from app.services.presence import PresenceService

router = APIRouter(prefix="/v1", tags=["friends"])


@router.get("/friends", response_model=list[PlayerBrief])
async def get_friends(
    player: AuthenticatedPlayer = Depends(get_current_player),
    session: AsyncSession = Depends(get_session),
    presence: PresenceService = Depends(get_presence_service),
):
    profiles = await friends.list_friends(session, player)
    return [
        PlayerBrief.model_validate(profile).model_copy(
            update={"is_online": await presence.is_online(profile.uid)}
        )
        for profile in profiles
    ]


@router.get("/friends/search", response_model=PlayerBrief)
async def search_friend(
    username: str | None = None,
    friend_code: str | None = None,
    player: AuthenticatedPlayer = Depends(get_current_player),
    session: AsyncSession = Depends(get_session),
    presence: PresenceService = Depends(get_presence_service),
):
    try:
        target = FriendTargetRequest(username=username, friend_code=friend_code)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    profile = (
        await friends.search_username(session, target.username)
        if target.username is not None
        else await friends.search_friend_code(session, target.friend_code)
    )
    if profile.uid == player.uid:
        raise GameplayError(409, "cannot_friend_self", "Your friend code belongs to you.")
    return PlayerBrief.model_validate(profile).model_copy(
        update={"is_online": await presence.is_online(profile.uid)}
    )


@router.get("/friend-requests", response_model=list[FriendRequestRead])
async def get_friend_requests(
    direction: str = Query(default="incoming", pattern=r"^(incoming|outgoing)$"),
    player: AuthenticatedPlayer = Depends(get_current_player),
    session: AsyncSession = Depends(get_session),
):
    requests = await friends.list_friend_requests(session, player, direction)
    return [
        FriendRequestRead(
            id=request.id,
            status=request.status,
            created_at=request.created_at,
            other_player=PlayerBrief.model_validate(sender),
        )
        for request, sender in requests
    ]


@router.post("/friend-requests", status_code=status.HTTP_201_CREATED, response_model=FriendRequestRead)
async def create_friend_request(
    payload: FriendTargetRequest,
    player: AuthenticatedPlayer = Depends(get_current_player),
    session: AsyncSession = Depends(get_session),
):
    request, recipient = await friends.send_friend_request(
        session, player, username=payload.username, friend_code=payload.friend_code
    )
    return FriendRequestRead(
        id=request.id,
        status=request.status,
        created_at=request.created_at,
        other_player=PlayerBrief.model_validate(recipient),
    )


@router.delete("/friend-requests/{request_id}")
async def cancel_friend_request(
    request_id: str,
    player: AuthenticatedPlayer = Depends(get_current_player),
    session: AsyncSession = Depends(get_session),
):
    request = await friends.cancel_friend_request(session, player, request_id)
    return {"id": request.id, "status": request.status}


@router.delete("/friends/{username}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_friend(
    username: str,
    player: AuthenticatedPlayer = Depends(get_current_player),
    session: AsyncSession = Depends(get_session),
):
    try:
        target = FriendTargetRequest(username=username)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await friends.remove_friend(session, player, target.username)


@router.post("/friend-requests/{request_id}/accept")
async def accept_friend_request(
    request_id: str,
    player: AuthenticatedPlayer = Depends(get_current_player),
    session: AsyncSession = Depends(get_session),
):
    request = await friends.accept_friend_request(session, player, request_id)
    return {"id": request.id, "status": request.status}


@router.post("/friend-requests/{request_id}/decline")
async def decline_friend_request(
    request_id: str,
    player: AuthenticatedPlayer = Depends(get_current_player),
    session: AsyncSession = Depends(get_session),
):
    request = await friends.decline_friend_request(session, player, request_id)
    return {"id": request.id, "status": request.status}
