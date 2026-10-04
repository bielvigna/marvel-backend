from redis.asyncio import Redis


class PresenceService:
    def __init__(self, redis: Redis, ttl_seconds: int = 90):
        self._redis = redis
        self._ttl_seconds = ttl_seconds

    @staticmethod
    def key_for(uid: str) -> str:
        return f"gameplay:presence:{uid}"

    async def touch(self, uid: str) -> None:
        await self._redis.set(self.key_for(uid), "1", ex=self._ttl_seconds)

    async def is_online(self, uid: str) -> bool:
        return bool(await self._redis.exists(self.key_for(uid)))
