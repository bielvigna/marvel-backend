from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import GameplayError
from app.core.firebase_auth import AuthenticatedPlayer
from app.db.models import ActiveMatchPlayer, Challenge, Match, MatchParticipant
from app.repositories.friends import pair_key
from app.repositories.matches import (
    get_active_match_player,
    get_friendship,
    get_incoming_challenges,
    get_match_participants,
    get_pending_challenge_for_pair,
)
from app.repositories.profiles import get_profile_by_code
from app.services.profiles import get_or_create_profile

CHALLENGE_TTL = timedelta(minutes=10)


def _now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


async def list_challenges(session: AsyncSession, player: AuthenticatedPlayer):
    await get_or_create_profile(session, player)
    result = await get_incoming_challenges(session, player.uid, _now())
    return [(challenge, profile) for challenge, profile in result]


async def create_challenge(session: AsyncSession, player: AuthenticatedPlayer, friend_code: str):
    sender = await get_or_create_profile(session, player)
    recipient = await get_profile_by_code(session, friend_code.upper())
    if recipient is None:
        raise GameplayError(404, "player_not_found", "No player has that friend code.")
    if sender.uid == recipient.uid:
        raise GameplayError(409, "cannot_challenge_self", "You cannot challenge yourself.")
    if await get_friendship(session, sender.uid, recipient.uid) is None:
        raise GameplayError(409, "friendship_required", "You can only challenge an accepted friend.")
    if await get_active_match_player(session, sender.uid) or await get_active_match_player(
        session, recipient.uid
    ):
        raise GameplayError(409, "player_in_match", "A player is already in an active match.")

    low, high = pair_key(sender.uid, recipient.uid)
    existing = await get_pending_challenge_for_pair(session, sender.uid, recipient.uid)
    if existing is not None:
        raise GameplayError(409, "challenge_exists", "A pending challenge already exists for this pair.")
    challenge = Challenge(
        id=str(uuid4()),
        sender_uid=sender.uid,
        recipient_uid=recipient.uid,
        pair_low=low,
        pair_high=high,
        status="pending",
        expires_at=_now() + CHALLENGE_TTL,
    )
    session.add(challenge)
    try:
        await session.commit()
        await session.refresh(challenge)
    except IntegrityError as exc:
        await session.rollback()
        raise GameplayError(
            409, "challenge_exists", "A pending challenge already exists for this pair."
        ) from exc
    return challenge, recipient


async def _resolve_challenge(
    session: AsyncSession, player: AuthenticatedPlayer, challenge_id: str, accept: bool
):
    challenge = await session.get(Challenge, challenge_id, with_for_update=True)
    if challenge is None:
        raise GameplayError(404, "challenge_not_found", "Battle challenge not found.")
    if challenge.recipient_uid != player.uid:
        raise GameplayError(
            403, "not_challenge_recipient", "Only the invited player can resolve this challenge."
        )
    if challenge.status != "pending":
        raise GameplayError(409, "challenge_resolved", "This challenge has already been resolved.")
    if _as_utc(challenge.expires_at) <= _now():
        challenge.status = "expired"
        await session.commit()
        raise GameplayError(410, "challenge_expired", "This battle challenge has expired.")
    if not accept:
        challenge.status = "declined"
        await session.commit()
        await session.refresh(challenge)
        return challenge, None

    for uid in (challenge.sender_uid, challenge.recipient_uid):
        if await get_active_match_player(session, uid) is not None:
            raise GameplayError(409, "player_in_match", "A player is already in an active match.")
    match = Match(id=str(uuid4()), mode="team_battle", status="awaiting_teams", state={"teams": {}})
    session.add(match)
    await session.flush()
    session.add_all(
        [
            MatchParticipant(match_id=match.id, player_uid=challenge.sender_uid, seat=0),
            MatchParticipant(match_id=match.id, player_uid=challenge.recipient_uid, seat=1),
            ActiveMatchPlayer(player_uid=challenge.sender_uid, match_id=match.id),
            ActiveMatchPlayer(player_uid=challenge.recipient_uid, match_id=match.id),
        ]
    )
    challenge.status = "accepted"
    challenge.match_id = match.id
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise GameplayError(409, "player_in_match", "A player is already in an active match.") from exc
    await session.refresh(challenge)
    await session.refresh(match)
    participants = list((await get_match_participants(session, match.id)).scalars())
    return challenge, (match, participants)


async def accept_challenge(session: AsyncSession, player: AuthenticatedPlayer, challenge_id: str):
    return await _resolve_challenge(session, player, challenge_id, True)


async def decline_challenge(session: AsyncSession, player: AuthenticatedPlayer, challenge_id: str):
    return await _resolve_challenge(session, player, challenge_id, False)
