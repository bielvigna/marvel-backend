from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import FriendRequest, Friendship, PlayerProfile


def pair_key(first_uid: str, second_uid: str) -> tuple[str, str]:
    return tuple(sorted((first_uid, second_uid)))


async def get_friendship(session: AsyncSession, first_uid: str, second_uid: str) -> Friendship | None:
    return await session.get(Friendship, pair_key(first_uid, second_uid))


async def get_request_for_pair(
    session: AsyncSession, first_uid: str, second_uid: str
) -> FriendRequest | None:
    low, high = pair_key(first_uid, second_uid)
    return await session.scalar(
        select(FriendRequest).where(FriendRequest.pair_low == low, FriendRequest.pair_high == high)
    )


async def get_incoming_requests(session: AsyncSession, uid: str):
    return await session.execute(
        select(FriendRequest, PlayerProfile)
        .join(PlayerProfile, PlayerProfile.uid == FriendRequest.requester_uid)
        .where(FriendRequest.recipient_uid == uid, FriendRequest.status == "pending")
        .order_by(FriendRequest.created_at)
    )


async def get_outgoing_requests(session: AsyncSession, uid: str):
    return await session.execute(
        select(FriendRequest, PlayerProfile)
        .join(PlayerProfile, PlayerProfile.uid == FriendRequest.recipient_uid)
        .where(FriendRequest.requester_uid == uid, FriendRequest.status == "pending")
        .order_by(FriendRequest.created_at)
    )


async def get_friends(session: AsyncSession, uid: str) -> list[PlayerProfile]:
    relation = or_(
        and_(Friendship.player_low_uid == uid, PlayerProfile.uid == Friendship.player_high_uid),
        and_(Friendship.player_high_uid == uid, PlayerProfile.uid == Friendship.player_low_uid),
    )
    result = await session.scalars(
        select(PlayerProfile).join(Friendship, relation).order_by(PlayerProfile.uid)
    )
    return list(result)
