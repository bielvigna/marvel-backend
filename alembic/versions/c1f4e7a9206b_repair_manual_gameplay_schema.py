"""Repair gameplay tables created from the original setup SQL.

Revision ID: c1f4e7a9206b
Revises: 4d90bca3e751
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c1f4e7a9206b"
down_revision: str | Sequence[str] | None = "4d90bca3e751"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

GAMEPLAY_TABLES = (
    "battle_challenges",
    "match_actions",
    "match_participants",
    "matchmaking_pairs",
    "active_match_players",
    "friendships",
    "friend_requests",
    "matches",
)


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names(schema="public"))

    # The original hand-written setup SQL created incompatible table shapes.
    # Refuse to rewrite any gameplay records if this repair is run later.
    for table in GAMEPLAY_TABLES:
        if table in existing:
            count = bind.execute(sa.text(f'SELECT COUNT(*) FROM public."{table}"')).scalar_one()
            if count:
                raise RuntimeError(
                    f"Refusing to rebuild {table}: it contains {count} row(s). "
                    "Back up and migrate those records before applying this schema repair."
                )

    for table in GAMEPLAY_TABLES:
        if table in existing:
            op.drop_table(table)

    op.create_table(
        "matches",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("mode", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("current_turn_uid", sa.String(length=128), nullable=True),
        sa.Column("turn_number", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("state", sa.JSON(), nullable=False),
        sa.Column("winner_uid", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["current_turn_uid"], ["player_profiles.uid"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["winner_uid"], ["player_profiles.uid"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_matches_status", "matches", ["status"])

    op.create_table(
        "friend_requests",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("pair_low", sa.String(length=128), nullable=False),
        sa.Column("pair_high", sa.String(length=128), nullable=False),
        sa.Column("requester_uid", sa.String(length=128), nullable=False),
        sa.Column("recipient_uid", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["pair_low"], ["player_profiles.uid"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["pair_high"], ["player_profiles.uid"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requester_uid"], ["player_profiles.uid"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recipient_uid"], ["player_profiles.uid"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("pair_low", "pair_high", name="uq_friend_request_pair"),
    )
    op.create_index("ix_friend_requests_pair_low", "friend_requests", ["pair_low"])
    op.create_index("ix_friend_requests_pair_high", "friend_requests", ["pair_high"])
    op.create_index("ix_friend_requests_status", "friend_requests", ["status"])

    op.create_table(
        "friendships",
        sa.Column("player_low_uid", sa.String(length=128), nullable=False),
        sa.Column("player_high_uid", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["player_low_uid"], ["player_profiles.uid"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["player_high_uid"], ["player_profiles.uid"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("player_low_uid", "player_high_uid"),
    )

    op.create_table(
        "battle_challenges",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("sender_uid", sa.String(length=128), nullable=False),
        sa.Column("recipient_uid", sa.String(length=128), nullable=False),
        sa.Column("pair_low", sa.String(length=128), nullable=False),
        sa.Column("pair_high", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("match_id", sa.String(length=36), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["sender_uid"], ["player_profiles.uid"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recipient_uid"], ["player_profiles.uid"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["pair_low"], ["player_profiles.uid"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["pair_high"], ["player_profiles.uid"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("pair_low", "pair_high", name="uq_challenge_pair"),
    )
    op.create_index("ix_battle_challenges_sender_uid", "battle_challenges", ["sender_uid"])
    op.create_index("ix_battle_challenges_recipient_uid", "battle_challenges", ["recipient_uid"])
    op.create_index("ix_battle_challenges_status", "battle_challenges", ["status"])

    op.create_table(
        "match_participants",
        sa.Column("match_id", sa.String(length=36), nullable=False),
        sa.Column("player_uid", sa.String(length=128), nullable=False),
        sa.Column("seat", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["player_uid"], ["player_profiles.uid"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("match_id", "player_uid"),
        sa.UniqueConstraint("match_id", "seat", name="uq_match_participant_seat"),
    )

    op.create_table(
        "active_match_players",
        sa.Column("player_uid", sa.String(length=128), nullable=False),
        sa.Column("match_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["player_uid"], ["player_profiles.uid"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("player_uid"),
    )
    op.create_index("ix_active_match_players_match_id", "active_match_players", ["match_id"])

    op.create_table(
        "matchmaking_pairs",
        sa.Column("pair_id", sa.String(length=36), nullable=False),
        sa.Column("match_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("pair_id"),
        sa.UniqueConstraint("match_id"),
    )

    op.create_table(
        "match_actions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("match_id", sa.String(length=36), nullable=False),
        sa.Column("player_uid", sa.String(length=128), nullable=False),
        sa.Column("client_action_id", sa.String(length=36), nullable=False),
        sa.Column("action_type", sa.String(length=24), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("resulting_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["player_uid"], ["player_profiles.uid"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("player_uid", "client_action_id", name="uq_match_action_idempotency"),
    )
    op.create_index("ix_match_actions_match_id", "match_actions", ["match_id"])


def downgrade() -> None:
    raise RuntimeError("This repair cannot be downgraded safely after gameplay data is created.")
