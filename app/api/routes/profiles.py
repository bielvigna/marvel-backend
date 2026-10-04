import hashlib
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.firebase_auth import AuthenticatedPlayer, get_current_player
from app.db.session import get_session
from app.schemas.profile import ProfilePatch, ProfileRead
from app.services.cloudinary_signing import create_upload_signature
from app.services.profiles import get_or_create_profile, update_profile

router = APIRouter(prefix="/v1/profile", tags=["profile"])


@router.post("/avatar-signature")
async def create_avatar_signature(
    request: Request,
    player: AuthenticatedPlayer = Depends(get_current_player),
):
    secret = request.app.state.settings.cloudinary_api_secret.strip()
    if not secret:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "cloudinary_unconfigured",
                "message": "Cloudinary upload signing is not configured on the server.",
            },
        )
    timestamp = int(time.time())
    uid_digest = hashlib.sha256(player.uid.encode("utf-8")).hexdigest()
    public_id = f"marvel_battlefield/avatars/{uid_digest}"
    signature = create_upload_signature(timestamp, secret, public_id)
    return {"timestamp": timestamp, "signature": signature, "public_id": public_id, "overwrite": True}


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
