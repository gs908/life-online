"""scn_task_template 加 difficulty / estimated_minutes 列(DEV-34 块 C)

押金改为耗时驱动(coin_service.resolve_deposit)、难度只影响 XP:
- difficulty: 1-5,默认 2(倍率 1.0,存量模板迁移后 XP 行为不变);
- estimated_minutes: 预计耗时(分钟),押金公式的输入,可空。

expand-only:两列均可空/带默认,存量行不做数据回填(开发验证阶段)。

Revision ID: a9f3d2c7e1b4
Revises: e8b2c4f6d9a1
Create Date: 2026-10-12 00:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a9f3d2c7e1b4"
down_revision: str | None = "e8b2c4f6d9a1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "scn_task_template",
        sa.Column("difficulty", sa.Integer(), nullable=False, server_default="2"),
    )
    op.add_column(
        "scn_task_template",
        sa.Column("estimated_minutes", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("scn_task_template", "estimated_minutes")
    op.drop_column("scn_task_template", "difficulty")
