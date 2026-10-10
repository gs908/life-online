"""add sys_channel_password

Revision ID: c7d1e4a9b3f2
Revises: b9e4f7c21a6d
Create Date: 2026-10-10 10:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c7d1e4a9b3f2"
down_revision: Union[str, None] = "b9e4f7c21a6d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sys_channel_password",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "account_id",
            sa.String(length=36),
            sa.ForeignKey("sys_account.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("username", sa.String(length=32), nullable=False),
        sa.Column("password_hash", sa.String(length=256), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        op.f("ix_sys_channel_password_account_id"),
        "sys_channel_password",
        ["account_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_sys_channel_password_username"),
        "sys_channel_password",
        ["username"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_sys_channel_password_username"), table_name="sys_channel_password"
    )
    op.drop_index(
        op.f("ix_sys_channel_password_account_id"), table_name="sys_channel_password"
    )
    op.drop_table("sys_channel_password")
