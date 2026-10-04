from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Challenge(Base):
    __tablename__ = "battle_challenges"
    __table_args__ = (UniqueConstraint("pair_low", "pair_high", name="uq_challenge_pair"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    sender_uid: Mapped[str] = mapped_column(ForeignKey("player_profiles.uid", ondelete="CASCADE"), index=True)
    recipient_uid: Mapped[str] = mapped_column(
        ForeignKey("player_profiles.uid", ondelete="CASCADE"), index=True
    )
    pair_low: Mapped[str] = mapped_column(ForeignKey("player_profiles.uid", ondelete="CASCADE"))
    pair_high: Mapped[str] = mapped_column(ForeignKey("player_profiles.uid", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    match_id: Mapped[str | None] = mapped_column(ForeignKey("matches.id", ondelete="SET NULL"), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
