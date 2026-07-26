"""scn_season: enforce single active season per family at db level

Revision ID: f3a1c9d02b7e
Revises: 8aa7c7e1f4d1
Create Date: 2026-07-27 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f3a1c9d02b7e"
down_revision: Union[str, None] = "8aa7c7e1f4d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "scn_season",
        sa.Column(
            "active_family_id",
            sa.String(length=36),
            sa.Computed("IF(is_active, family_id, NULL)", persisted=True),
            nullable=True,
        ),
    )
    op.create_index(
        op.f("ux_scn_season_active_per_family"),
        "scn_season",
        ["active_family_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(op.f("ux_scn_season_active_per_family"), table_name="scn_season")
    op.drop_column("scn_season", "active_family_id")
