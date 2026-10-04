from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import GameplayError
from app.core.firebase_auth import AuthenticatedPlayer
from app.db.models import FriendRequest, Friendship
from app.repositories.friends import (
    get_friends,
    get_friendship,
    get_incoming_requests,
    get_outgoing_requests,
    get_request_for_pair,
    pair_key,
)
from app.repositories.profiles import get_profile_by_code, get_profile_by_username
from app.services.profiles import get_or_create_profile


async def search_friend_code(session: AsyncSession, friend_code: str):
    profile = await get_profile_by_code(session, friend_code)
    if profile is None:
        raise GameplayError(404, "player_not_found", "No player has that friend code.")
    return profile


async def search_username(session: AsyncSession, username: str):
    profile = await get_profile_by_username(session, username)
    if profile is None:
        raise GameplayError(404, "player_not_found", "No player has that username.")
    return profile


async def list_friends(session: AsyncSession, player: AuthenticatedPlayer):
    await get_or_create_profile(session, player)
    return await get_friends(session, player.uid)


async def list_friend_requests(
    session: AsyncSession, player: AuthenticatedPlayer, direction: str = "incoming"
):
    await get_or_create_profile(session, player)
    result = (
        await get_outgoing_requests(session, player.uid)
        if direction == "outgoing"
        else await get_incoming_requests(session, player.uid)
    )
    return [(request, profile) for request, profile in result]


async def send_friend_request(
    session: AsyncSession,
    player: AuthenticatedPlayer,
    *,
    username: str | None = None,
    friend_code: str | None = None,
):
    requester = await get_or_create_profile(session, player)
    recipient = (
        await search_username(session, username)
        if username is not None
        else await search_friend_code(session, friend_code)
    )
    if requester.uid == recipient.uid:
        raise GameplayError(409, "cannot_friend_self", "You cannot send a friend request to yourself.")
    if await get_friendship(session, requester.uid, recipient.uid):
        raise GameplayError(409, "already_friends", "These players are already friends.")

    existing = await get_request_for_pair(session, requester.uid, recipient.uid)
    if existing and existing.status == "pending":
        raise GameplayError(409, "friend_request_exists", "A pending friend request already exists.")
    if existing and existing.status == "accepted":
        raise GameplayError(409, "already_friends", "These players are already friends.")
    low, high = pair_key(requester.uid, recipient.uid)
    if existing:
        existing.requester_uid = requester.uid
        existing.recipient_uid = recipient.uid
        existing.status = "pending"
    else:
        existing = FriendRequest(
            id=str(uuid4()),
            pair_low=low,
            pair_high=high,
            requester_uid=requester.uid,
            recipient_uid=recipient.uid,
            status="pending",
        )
        session.add(existing)
    try:
        await session.commit()
        await session.refresh(existing)
    except IntegrityError as exc:
        await session.rollback()
        raise GameplayError(
            409, "friend_request_exists", "A request for this player pair already exists."
        ) from exc
    return existing, recipient


async def cancel_friend_request(session: AsyncSession, player: AuthenticatedPlayer, request_id: str):
    request = await session.get(FriendRequest, request_id, with_for_update=True)
    if request is None:
        raise GameplayError(404, "friend_request_not_found", "Friend request not found.")
    if request.requester_uid != player.uid:
        raise GameplayError(403, "not_request_requester", "Only the requester can cancel this request.")
    if request.status != "pending":
        raise GameplayError(409, "friend_request_resolved", "This friend request has already been resolved.")
    request.status = "canceled"
    await session.commit()
    return request


async def remove_friend(session: AsyncSession, player: AuthenticatedPlayer, username: str):
    target = await search_username(session, username)
    if target.uid == player.uid:
        raise GameplayError(409, "cannot_friend_self", "You cannot remove yourself as a friend.")
    friendship = await get_friendship(session, player.uid, target.uid)
    if friendship is None:
        return
    await session.delete(friendship)
    request = await get_request_for_pair(session, player.uid, target.uid)
    if request is not None and request.status == "accepted":
        request.status = "removed"
    await session.commit()


async def _resolve_friend_request(
    session: AsyncSession, player: AuthenticatedPlayer, request_id: str, accepted: bool
):
    request = await session.get(FriendRequest, request_id, with_for_update=True)
    if request is None:
        raise GameplayError(404, "friend_request_not_found", "Friend request not found.")
    if request.recipient_uid != player.uid:
        raise GameplayError(403, "not_request_recipient", "Only the recipient can resolve this request.")
    if request.status != "pending":
        raise GameplayError(409, "friend_request_resolved", "This friend request has already been resolved.")
    request.status = "accepted" if accepted else "declined"
    if accepted:
        session.add(Friendship(player_low_uid=request.pair_low, player_high_uid=request.pair_high))
    try:
        await session.commit()
        await session.refresh(request)
    except IntegrityError as exc:
        await session.rollback()
        raise GameplayError(
            409, "friend_request_resolved", "This friend request has already been resolved."
        ) from exc
    return request


async def accept_friend_request(session: AsyncSession, player: AuthenticatedPlayer, request_id: str):
    return await _resolve_friend_request(session, player, request_id, True)


async def decline_friend_request(session: AsyncSession, player: AuthenticatedPlayer, request_id: str):
    return await _resolve_friend_request(session, player, request_id, False)
