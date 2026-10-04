import os
from dataclasses import dataclass
from types import SimpleNamespace

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@dataclass(frozen=True)
class FakePlayer:
    uid: str
    email: str | None = None
    display_name: str | None = None


class FakeTokenVerifier:
    def verify(self, token: str) -> dict[str, str]:
        if token == "valid-token":
            return {"uid": "player-1", "email": "one@example.test", "name": "One"}
        if token == "player-two":
            return {"uid": "player-2", "email": "two@example.test", "name": "Two"}
        if token == "player-three":
            return {"uid": "player-3", "email": "three@example.test", "name": "Three"}
        raise ValueError("bad token")


class FakeCharacterCatalog:
    async def get_character(self, character_id: int):
        types = {1: ["BRUTE"], 2: ["TECH"], 3: ["MYSTIC"], 4: ["AGILE"], 5: ["ENERGY"], 6: ["MARTIAL"]}
        if character_id not in types:
            return None
        return SimpleNamespace(
            id=character_id,
            name=f"Hero {character_id}",
            image_url=f"https://images.example.test/{character_id}.jpg",
            types=types[character_id],
        )


@pytest.fixture
def app():
    app = create_app(token_verifier=FakeTokenVerifier())
    app.state.character_provider = FakeCharacterCatalog()

    async def ready():
        return None

    app.state.ready_checks = {"postgres": ready, "redis": ready}
    return app


@pytest_asyncio.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as test_client:
        yield test_client


@pytest_asyncio.fixture
async def database_client(app, tmp_path):
    import fakeredis.aioredis
    from redis.asyncio import Redis
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.db import models as _models  # noqa: F401
    from app.db.base import Base

    database_url = os.getenv("GAMEPLAY_TEST_DATABASE_URL")
    redis_url = os.getenv("GAMEPLAY_TEST_REDIS_URL")
    engine = create_async_engine(database_url or f"sqlite+aiosqlite:///{tmp_path / 'gameplay-tests.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    app.state.engine = engine
    app.state.session_factory = async_sessionmaker(engine, expire_on_commit=False)
    if redis_url:
        app.state.redis_client = Redis.from_url(redis_url, decode_responses=True)
        await app.state.redis_client.flushdb()
    else:
        app.state.redis_client = fakeredis.aioredis.FakeRedis(decode_responses=True)

    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as async_client:
            yield async_client
