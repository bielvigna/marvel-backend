import re
from datetime import datetime

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator, model_validator


class ProfilePatch(BaseModel):
    nickname: str | None = Field(default=None, max_length=32)
    username: str | None = None
    avatar_url: AnyHttpUrl | None = None

    @field_validator("username", mode="before")
    @classmethod
    def reject_null_username(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("Username cannot be null")
        return value

    @field_validator("nickname")
    @classmethod
    def normalize_nickname(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Nickname cannot be empty")
        return value

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().lower()
        if re.fullmatch(r"[a-z0-9_]{3,20}", value) is None:
            raise ValueError("Username must contain 3–20 ASCII letters, digits, or underscores")
        return value


class ProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uid: str
    email: str | None
    display_name: str | None
    nickname: str | None
    username: str | None
    friend_code: str
    avatar_url: str | None
    created_at: datetime


class PlayerBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    friend_code: str
    username: str | None
    nickname: str | None
    display_name: str | None
    avatar_url: str | None
    is_online: bool = False


class FriendCodeRequest(BaseModel):
    friend_code: str = Field(min_length=8, max_length=8, pattern=r"^[A-Za-z0-9]{8}$")

    @field_validator("friend_code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.upper()


class FriendTargetRequest(BaseModel):
    username: str | None = None
    friend_code: str | None = Field(default=None, min_length=8, max_length=8, pattern=r"^[A-Za-z0-9]{8}$")

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str | None) -> str | None:
        return ProfilePatch.normalize_username(value)

    @field_validator("friend_code")
    @classmethod
    def normalize_code(cls, value: str | None) -> str | None:
        return value.upper() if value is not None else None

    @model_validator(mode="after")
    def exactly_one_target(self):
        if (self.username is None) == (self.friend_code is None):
            raise ValueError("Supply exactly one of username or friend_code")
        return self


class FriendRequestRead(BaseModel):
    id: str
    status: str
    created_at: datetime
    other_player: PlayerBrief
