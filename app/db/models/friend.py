from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FriendRequest(Base):
    __tablename__ = "friend_requests"
    __table_args__ = (UniqueConstraint("pair_low", "pair_high", name="uq_friend_request_pair"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    pair_low: Mapped[str] = mapped_column(ForeignKey("player_profiles.uid", ondelete="CASCADE"), index=True)
    pair_high: Mapped[str] = mapped_column(ForeignKey("player_profiles.uid", ondelete="CASCADE"), index=True)
    requester_uid: Mapped[str] = mapped_column(ForeignKey("player_profiles.uid", ondelete="CASCADE"))
    recipient_uid: Mapped[str] = mapped_column(ForeignKey("player_profiles.uid", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Friendship(Base):
    __tablename__ = "friendships"

    player_low_uid: Mapped[str] = mapped_column(
        ForeignKey("player_profiles.uid", ondelete="CASCADE"), primary_key=True
    )
    player_high_uid: Mapped[str] = mapped_column(
        ForeignKey("player_profiles.uid", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
