from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PlayerProfile


async def get_profile(session: AsyncSession, uid: str) -> PlayerProfile | None:
    return await session.get(PlayerProfile, uid)


async def get_profile_by_code(session: AsyncSession, friend_code: str) -> PlayerProfile | None:
    statement = select(PlayerProfile).where(PlayerProfile.friend_code == friend_code.upper())
    return await session.scalar(statement)


async def get_profile_by_username(session: AsyncSession, username: str) -> PlayerProfile | None:
    statement = select(PlayerProfile).where(func.lower(PlayerProfile.username) == username.lower())
    return await session.scalar(statement)


async def save_profile(session: AsyncSession, profile: PlayerProfile) -> PlayerProfile:
    session.add(profile)
    await session.commit()
    await session.refresh(profile)
    return profile
