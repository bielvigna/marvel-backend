from collections.abc import AsyncIterator

from fastapi import HTTPException, Request, status
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings, get_settings


def make_engine(settings: Settings | None = None):
    settings = settings or get_settings()
    database_url = make_url(settings.database_url)
    if database_url.drivername in {"postgres", "postgresql"}:
        database_url = database_url.set(drivername="postgresql+asyncpg")
    return create_async_engine(database_url, pool_pre_ping=True)


def make_session_factory(engine):
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "database_unavailable", "message": "The gameplay database is unavailable."},
        )
    async with factory() as session:
        yield session
