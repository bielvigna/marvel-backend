import json
from dataclasses import dataclass

import httpx
from redis.asyncio import Redis

from app.core.errors import GameplayError
from app.domain.battle_rules import BattleRules


@dataclass(frozen=True)
class CatalogCharacter:
    id: int
    name: str
    image_url: str | None
    types: list[str]


class CharacterCatalogClient:
    def __init__(self, base_url: str, redis: Redis, timeout_seconds: float = 3.0):
        self.base_url = base_url.rstrip("/")
        self.redis = redis
        self.timeout_seconds = timeout_seconds

    async def get_character(self, character_id: int) -> CatalogCharacter | None:
        cache_key = f"gameplay:catalog:character:{character_id}"
        cached = await self.redis.get(cache_key)
        if cached:
            data = json.loads(cached)
            return CatalogCharacter(**data) if data else None
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(f"{self.base_url}/api/characters/{character_id}")
        except httpx.HTTPError as exc:
            raise GameplayError(
                503, "character_catalog_unavailable", "The character catalog is unavailable."
            ) from exc
        if response.status_code == 404:
            await self.redis.set(cache_key, "null", ex=300)
            return None
        if response.is_error:
            raise GameplayError(503, "character_catalog_unavailable", "The character catalog is unavailable.")
        try:
            data = response.json()
            character = CatalogCharacter(
                id=int(data["id"]),
                name=str(data["name"]),
                image_url=data.get("image_url"),
                types=BattleRules.map_powers([str(power) for power in data.get("powers", [])]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise GameplayError(
                503, "invalid_character_catalog_response", "The character catalog returned invalid data."
            ) from exc
        await self.redis.set(cache_key, json.dumps(character.__dict__), ex=86400)
        return character
