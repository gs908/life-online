"""scn_season: enforce single active season per family at db level (PostgreSQL)

Revision ID: f3a1c9d02b7e
Revises: 8aa7c7e1f4d1
Create Date: 2026-07-27 00:00:00.000000

PostgreSQL 版本:用部分唯一索引(partial unique index)在数据库层面兜底
"同一家庭同时只能有一个激活赛季"。相比 MySQL 版的生成列方案,不需要
额外列,索引也只覆盖 is_active 行。
该 revision 与 DEV-4~9 工作分支上的 f3a1c9d02b7e 是同一逻辑变更的
PostgreSQL 改写(原版使用 MySQL IF() 生成列,在 Supabase 上无法执行);
分支合入/变基时以本文件为准,并同步调整模型(见 PR 说明)。
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
    op.create_index(
        op.f("ux_scn_season_active_per_family"),
        "scn_season",
        ["family_id"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )


def downgrade() -> None:
    op.drop_index(op.f("ux_scn_season_active_per_family"), table_name="scn_season")
