from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ActiveMatchPlayer, Challenge, Match, MatchParticipant, PlayerProfile


async def get_incoming_challenges(session: AsyncSession, uid: str, now):
    return await session.execute(
        select(Challenge, PlayerProfile)
        .join(PlayerProfile, PlayerProfile.uid == Challenge.sender_uid)
        .where(Challenge.recipient_uid == uid, Challenge.status == "pending", Challenge.expires_at > now)
        .order_by(Challenge.created_at)
    )


async def get_active_match_player(session: AsyncSession, uid: str) -> ActiveMatchPlayer | None:
    return await session.get(ActiveMatchPlayer, uid)


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
