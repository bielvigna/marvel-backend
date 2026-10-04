import secrets

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import GameplayError
from app.core.firebase_auth import AuthenticatedPlayer
from app.db.models import PlayerProfile
from app.repositories.profiles import get_profile, get_profile_by_username, save_profile


async def get_or_create_profile(session: AsyncSession, player: AuthenticatedPlayer) -> PlayerProfile:
    profile = await get_profile(session, player.uid)
    if profile is not None:
        changed = False
        if player.email and profile.email != player.email:
            profile.email = player.email
            changed = True
        if player.display_name and profile.display_name != player.display_name:
            profile.display_name = player.display_name
            changed = True
        if changed:
            await session.commit()
            await session.refresh(profile)
        return profile

    for _ in range(5):
        profile = PlayerProfile(
            uid=player.uid,
            email=player.email,
            display_name=player.display_name,
            friend_code=secrets.token_hex(4).upper(),
        )
        try:
            return await save_profile(session, profile)
        except IntegrityError:
            await session.rollback()
            profile = await get_profile(session, player.uid)
            if profile is not None:
                return profile
    raise GameplayError(503, "profile_unavailable", "The player profile could not be initialized.")


async def update_profile(session: AsyncSession, player: AuthenticatedPlayer, updates: dict) -> PlayerProfile:
    profile = await get_or_create_profile(session, player)
    username = updates.get("username")
    if username is not None:
        owner = await get_profile_by_username(session, username)
        if owner is not None and owner.uid != player.uid:
            raise GameplayError(409, "username_taken", "This username is already taken.")
    for field, value in updates.items():
        setattr(profile, field, str(value) if field == "avatar_url" and value is not None else value)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        if username is not None:
            raise GameplayError(409, "username_taken", "This username is already taken.") from exc
        raise
    await session.refresh(profile)
    return profile
