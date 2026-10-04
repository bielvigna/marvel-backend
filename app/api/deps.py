from fastapi import Depends, HTTPException, Request, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.services.character_catalog import CharacterCatalogClient
from app.services.matches import MatchService
from app.services.matchmaking import MatchmakingService
from app.services.presence import PresenceService


async def get_redis(request: Request) -> Redis:
    redis = getattr(request.app.state, "redis_client", None)
    if redis is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "redis_unavailable", "message": "The gameplay queue is unavailable."},
        )
    return redis


async def get_matchmaking_service(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> MatchmakingService:
    redis = await get_redis(request)
    return MatchmakingService(session, redis)


async def get_presence_service(request: Request) -> PresenceService:
    redis = await get_redis(request)
    return PresenceService(redis)


async def get_character_provider(request: Request):
    provider = getattr(request.app.state, "character_provider", None)
    if provider is not None:
        return provider
    return CharacterCatalogClient(request.app.state.settings.character_api_base_url, await get_redis(request))


async def get_match_service(
    request: Request,
    session: AsyncSession = Depends(get_session),
    catalog=Depends(get_character_provider),
) -> MatchService:
    return MatchService(session, catalog, rng=getattr(request.app.state, "battle_rng", None))
