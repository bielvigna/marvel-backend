from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.firebase_auth import AuthenticatedPlayer, get_current_player
from app.db.session import get_session
from app.schemas.profile import ProfilePatch, ProfileRead
from app.services.profiles import get_or_create_profile, update_profile

router = APIRouter(prefix="/v1/profile", tags=["profile"])


@router.get("/me")
async def get_my_profile(
    player: AuthenticatedPlayer = Depends(get_current_player),
    session: AsyncSession = Depends(get_session),
):
    return await get_or_create_profile(session, player)


@router.patch("/me", response_model=ProfileRead)
async def patch_my_profile(
    payload: ProfilePatch,
    player: AuthenticatedPlayer = Depends(get_current_player),
    session: AsyncSession = Depends(get_session),
):
    updates = payload.model_dump(exclude_unset=True)
    return await update_profile(session, player, updates)
