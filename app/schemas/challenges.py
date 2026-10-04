from datetime import datetime

from pydantic import BaseModel

from app.schemas.profile import FriendCodeRequest, PlayerBrief


class ChallengeCreate(FriendCodeRequest):
    pass


class ChallengeRead(BaseModel):
    id: str
    status: str
    expires_at: datetime
    opponent: PlayerBrief


class MatchBrief(BaseModel):
    id: str
    status: str
    participants: list[PlayerBrief]


class ChallengeAcceptance(BaseModel):
    status: str
    match: MatchBrief
