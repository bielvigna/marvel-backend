from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    mode: Mapped[str] = mapped_column(String(24), nullable=False, default="team_battle")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="awaiting_teams", index=True)
    current_turn_uid: Mapped[str | None] = mapped_column(
        ForeignKey("player_profiles.uid", ondelete="SET NULL"), nullable=True
    )
    turn_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    state: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    winner_uid: Mapped[str | None] = mapped_column(
        ForeignKey("player_profiles.uid", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class MatchParticipant(Base):
    __tablename__ = "match_participants"
    __table_args__ = (UniqueConstraint("match_id", "seat", name="uq_match_participant_seat"),)

    match_id: Mapped[str] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), primary_key=True)
    player_uid: Mapped[str] = mapped_column(
        ForeignKey("player_profiles.uid", ondelete="CASCADE"), primary_key=True
    )
    seat: Mapped[int] = mapped_column(Integer, nullable=False)


class ActiveMatchPlayer(Base):
    __tablename__ = "active_match_players"

    player_uid: Mapped[str] = mapped_column(
        ForeignKey("player_profiles.uid", ondelete="CASCADE"), primary_key=True
    )
    match_id: Mapped[str] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), index=True)


class MatchmakingPair(Base):
    __tablename__ = "matchmaking_pairs"

    pair_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    match_id: Mapped[str] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), unique=True)


class MatchAction(Base):
    __tablename__ = "match_actions"
    __table_args__ = (UniqueConstraint("player_uid", "client_action_id", name="uq_match_action_idempotency"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    match_id: Mapped[str] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), index=True)
    player_uid: Mapped[str] = mapped_column(ForeignKey("player_profiles.uid", ondelete="CASCADE"))
    client_action_id: Mapped[str] = mapped_column(String(36), nullable=False)
    action_type: Mapped[str] = mapped_column(String(24), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    result_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    resulting_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
