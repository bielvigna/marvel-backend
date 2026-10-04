from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class TeamSubmission(BaseModel):
    character_ids: list[int] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def require_distinct_characters(self):
        if len(set(self.character_ids)) != len(self.character_ids):
            raise ValueError("Each character can only be selected once.")
        return self


class MatchActionRequest(BaseModel):
    action_id: UUID
    expected_version: int = Field(ge=0)
    action: Literal["attack", "ability", "defend", "switch", "use_item"]
    switch_index: int | None = Field(default=None, ge=0, le=2)
    item: Literal["health_potion", "shield", "ability_charge"] | None = None


class MatchActionResponse(BaseModel):
    event: dict
    match: dict
