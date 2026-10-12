"""scn_task_template 限时时间窗 / 实例池 / 废弃审计字段(DEV-35 块 A)

- timed_mode(NONE/DEADLINE/DURATION) + deadline_time/start_time/duration_minutes:
  限时任务时间窗;一致性由 schema 层创建/更新校验(422),非限时实例 expire_at 为 NULL。
- pool_policy: 实例池策略,默认 REUSE_UNTIL_CONSUMED(docs/12 决策 D1)。
- deprecated_at / deprecated_reason: 废弃审计;deprecated_at 非空即停用,生成器跳过。

estimated_minutes / difficulty 由 develop 侧 a9f3d2c7e1b4(DEV-34 块 C)建列,
本迁移不再重复 add_column;difficulty 在此放宽为可空(块 A 契约:未评星=NULL,
docs/04 口径 NULL 时 XP 倍率 1.0,与 difficulty=2 等价),并去掉 server_default,
与模型声明(nullable=True,无服务端默认)对齐。

Revision ID: b4d8f2a6c9e1
Revises: a7c3e1f5b2d8
Create Date: 2026-10-12 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b4d8f2a6c9e1"
down_revision: Union[str, None] = "a7c3e1f5b2d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "scn_task_template",
        sa.Column("timed_mode", sa.String(16), nullable=False, server_default="NONE"),
    )
    op.add_column("scn_task_template", sa.Column("deadline_time", sa.Time(), nullable=True))
    op.add_column("scn_task_template", sa.Column("start_time", sa.Time(), nullable=True))
    op.add_column("scn_task_template", sa.Column("duration_minutes", sa.Integer(), nullable=True))
    op.add_column(
        "scn_task_template",
        sa.Column(
            "pool_policy",
            sa.String(24),
            nullable=False,
            server_default="REUSE_UNTIL_CONSUMED",
        ),
    )
    op.add_column(
        "scn_task_template",
        sa.Column("deprecated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("scn_task_template", sa.Column("deprecated_reason", sa.String(128), nullable=True))
    # difficulty/estimated_minutes 已由 a9f3d2c7e1b4(DEV-34 块 C)建列,不再重复
    # add_column;这里只把 difficulty 放宽为可空并删 server_default,与块 A 模型
    # 契约(未评星=NULL)对齐。该 alter 对"已跑过 a9f3d2c7e1b4 的库"与"全新库"皆成立。
    op.alter_column(
        "scn_task_template",
        "difficulty",
        existing_type=sa.Integer(),
        nullable=True,
        server_default=None,
        existing_server_default=sa.text("'2'"),
        existing_nullable=False,
        comment="难度 1-5",
    )


def downgrade() -> None:
    op.drop_column("scn_task_template", "deprecated_reason")
    op.drop_column("scn_task_template", "deprecated_at")
    # 恢复非空约束前先把 NULL 难度收敛回默认 2(a9f3d2c7e1b4 的口径)。
    op.execute("UPDATE scn_task_template SET difficulty = 2 WHERE difficulty IS NULL")
    op.alter_column(
        "scn_task_template",
        "difficulty",
        existing_type=sa.Integer(),
        nullable=False,
        server_default=sa.text("'2'"),
        existing_nullable=True,
        comment=None,
    )
    op.drop_column("scn_task_template", "pool_policy")
    op.drop_column("scn_task_template", "duration_minutes")
    op.drop_column("scn_task_template", "start_time")
    op.drop_column("scn_task_template", "deadline_time")
    op.drop_column("scn_task_template", "timed_mode")
