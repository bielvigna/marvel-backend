import pytest

from app.services.presence import PresenceService


@pytest.mark.asyncio
async def test_presence_is_refreshed_and_expires_from_redis():
    from fakeredis.aioredis import FakeRedis

    redis = FakeRedis(decode_responses=True)
    presence = PresenceService(redis, ttl_seconds=1)

    assert await presence.is_online("player-1") is False
    await presence.touch("player-1")
    assert await presence.is_online("player-1") is True
    await redis.delete(presence.key_for("player-1"))
    assert await presence.is_online("player-1") is False
    await redis.aclose()
