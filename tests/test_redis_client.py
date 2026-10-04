import pytest

from app.core.config import Settings
from app.core.redis_client import UpstashRedisAdapter, create_redis_client


class FakeUpstashClient:
    def __init__(self):
        self.eval_call = None
        self.closed = False

    async def eval(self, script, *, keys, args):
        self.eval_call = (script, keys, args)
        return ["waiting", "ticket"]

    async def aclose(self):
        self.closed = True


@pytest.mark.asyncio
async def test_adapter_translates_redis_py_eval_arguments_for_upstash_sdk():
    underlying = FakeUpstashClient()
    redis = UpstashRedisAdapter(underlying)

    result = await redis.eval("return ARGV[1]", 2, "key-1", "key-2", "arg-1")

    assert result == ["waiting", "ticket"]
    assert underlying.eval_call == ("return ARGV[1]", ["key-1", "key-2"], ["arg-1"])


@pytest.mark.asyncio
async def test_adapter_closes_the_underlying_upstash_client():
    underlying = FakeUpstashClient()
    await UpstashRedisAdapter(underlying).aclose()
    assert underlying.closed


def test_redis_factory_uses_upstash_rest_credentials_when_configured():
    settings = Settings(
        _env_file=None,
        redis_url="redis://localhost:6379/1",
        upstash_redis_rest_url="https://redis.example.test",
        upstash_redis_rest_token="test-token",
    )
    calls = []
    fake_client = FakeUpstashClient()

    def factory(**kwargs):
        calls.append(kwargs)
        return fake_client

    redis = create_redis_client(settings, upstash_client_factory=factory)

    assert isinstance(redis, UpstashRedisAdapter)
    assert calls == [{
        "url": "https://redis.example.test",
        "token": "test-token",
        "allow_telemetry": False,
    }]


def test_redis_factory_rejects_incomplete_upstash_credentials():
    settings = Settings(_env_file=None, upstash_redis_rest_url="https://redis.example.test")

    with pytest.raises(ValueError, match="UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN"):
        create_redis_client(settings)
