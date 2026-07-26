"""add account locale

Revision ID: 8aa7c7e1f4d1
Revises: d4a5b93011d5
Create Date: 2026-07-26 02:30:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8aa7c7e1f4d1"
down_revision: Union[str, None] = "d4a5b93011d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sys_account",
        sa.Column("locale", sa.String(length=16), nullable=False, server_default="zh-CN"),
    )
    op.alter_column("sys_account", "locale", server_default=None)


def downgrade() -> None:
    op.drop_column("sys_account", "locale")
