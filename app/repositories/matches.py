from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ActiveMatchPlayer, Challenge, Match, MatchParticipant, PlayerProfile

MATCH_INACTIVITY_TIMEOUT = timedelta(minutes=10)


async def get_incoming_challenges(session: AsyncSession, uid: str, now):
    return await session.execute(
        select(Challenge, PlayerProfile)
        .join(PlayerProfile, PlayerProfile.uid == Challenge.sender_uid)
        .where(Challenge.recipient_uid == uid, Challenge.status == "pending", Challenge.expires_at > now)
        .order_by(Challenge.created_at)
    )


async def get_active_match_player(session: AsyncSession, uid: str) -> ActiveMatchPlayer | None:
    active = await session.get(ActiveMatchPlayer, uid)
    if active is None:
        return None
    match = await session.get(Match, active.match_id)
    if match is None:
        await session.delete(active)
        await session.commit()
        return None
    if await expire_inactive_match(session, match):
        return None
    if match.status not in ("awaiting_teams", "active"):
        await session.delete(active)
        await session.commit()
        return None
    return active


def is_match_inactive(match: Match, now: datetime | None = None) -> bool:
    if match.status not in {"awaiting_teams", "active"}:
        return False
    last_activity = match.updated_at or match.created_at
    if last_activity is None:
        return False
    if last_activity.tzinfo is None:
        last_activity = last_activity.replace(tzinfo=timezone.utc)
    return last_activity <= (now or datetime.now(timezone.utc)) - MATCH_INACTIVITY_TIMEOUT


async def expire_inactive_match(
    session: AsyncSession, match: Match, now: datetime | None = None
) -> bool:
    if not is_match_inactive(match, now):
        return False
    match.status = "expired"
    match.current_turn_uid = None
    await session.execute(
        ActiveMatchPlayer.__table__.delete().where(ActiveMatchPlayer.match_id == match.id)
    )
    await session.commit()
    return True


async def get_match_participants(session: AsyncSession, match_id: str):
    return await session.execute(
        select(PlayerProfile)
        .join(MatchParticipant, MatchParticipant.player_uid == PlayerProfile.uid)
        .where(MatchParticipant.match_id == match_id)
        .order_by(MatchParticipant.seat)
    )


async def get_match(session: AsyncSession, match_id: str) -> Match | None:
    return await session.get(Match, match_id)


async def get_pending_challenge_for_pair(session: AsyncSession, first_uid: str, second_uid: str):
    low, high = sorted((first_uid, second_uid))
    return await session.scalar(
        select(Challenge)
        .where(
            Challenge.pair_low == low,
            Challenge.pair_high == high,
            Challenge.status == "pending",
        )
        .with_for_update()
    )


async def get_friendship(session: AsyncSession, first_uid: str, second_uid: str):
    from app.db.models import Friendship

    low, high = sorted((first_uid, second_uid))
    return await session.get(Friendship, (low, high))
