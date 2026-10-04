from collections.abc import Callable
from typing import Any

from redis.asyncio import Redis as RedisPyClient

from app.core.config import Settings


class UpstashRedisAdapter:
    """Expose the redis-py command signatures over the Upstash REST SDK."""

    def __init__(self, client: Any):
        self._client = client

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)

    async def eval(self, script: str, numkeys: int, *keys_and_args: Any) -> Any:
        keys = list(keys_and_args[:numkeys])
        args = list(keys_and_args[numkeys:])
        return await self._client.eval(script, keys=keys, args=args)

    async def aclose(self) -> None:
        close = getattr(self._client, "aclose", None) or getattr(self._client, "close", None)
        if close is not None:
            result = close()
            if hasattr(result, "__await__"):
                await result


def create_redis_client(
    settings: Settings,
    *,
    upstash_client_factory: Callable[..., Any] | None = None,
) -> Any:
    rest_url = settings.upstash_redis_rest_url.strip()
    rest_token = settings.upstash_redis_rest_token.strip()
    if rest_url or rest_token:
        if not rest_url or not rest_token:
            raise ValueError("Both UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN are required.")
        if upstash_client_factory is None:
            from upstash_redis.asyncio import Redis as UpstashRedis

            upstash_client_factory = UpstashRedis
        return UpstashRedisAdapter(
            upstash_client_factory(
                url=rest_url,
                token=rest_token,
                allow_telemetry=False,
            )
        )
    return RedisPyClient.from_url(settings.redis_url, decode_responses=True)
