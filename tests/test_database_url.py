import pytest

from app.core.config import Settings
from app.db.session import make_engine


@pytest.mark.parametrize(
    "database_url",
    [
        "postgres://user:pass@db.example.test:5432/gameplay",
        "postgresql://user:pass@db.example.test:5432/gameplay",
    ],
)
@pytest.mark.asyncio
async def test_make_engine_normalizes_render_postgres_urls(database_url):
    engine = make_engine(Settings(_env_file=None, database_url=database_url))
    try:
        assert engine.url.drivername == "postgresql+asyncpg"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_make_engine_keeps_explicit_asyncpg_url():
    url = "postgresql+asyncpg://user:pass@db.example.test:5432/gameplay"
    engine = make_engine(Settings(_env_file=None, database_url=url))
    try:
        assert engine.url.drivername == "postgresql+asyncpg"
    finally:
        await engine.dispose()
