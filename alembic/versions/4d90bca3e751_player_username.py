"""Add optional player username with case-insensitive uniqueness.

Revision ID: 4d90bca3e751
Revises: aa735a0061dc
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "4d90bca3e751"
down_revision: str | Sequence[str] | None = "aa735a0061dc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("player_profiles", sa.Column("username", sa.String(length=20), nullable=True))
    op.create_index(
        "ix_player_profiles_username_lower",
        "player_profiles",
        [sa.text("lower(username)")],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_player_profiles_username_lower", table_name="player_profiles")
    op.drop_column("player_profiles", "username")
