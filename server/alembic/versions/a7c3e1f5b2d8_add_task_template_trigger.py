"""scn_task_template_trigger 触发规则表(DEV-35 块 A)

一个模板多组触发规则(每日 / 指定星期 / 每月某日 / cron / 一次性),
生成器(app/services/task_generator_service.py)按规则幂等生成实例。
expand-only:新表,无存量数据迁移。

Revision ID: a7c3e1f5b2d8
Revises: a9f3d2c7e1b4
Create Date: 2026-10-12 00:00:00.000000

链说明(DEV-41 集成):down_revision 原为 e8b2c4f6d9a1,与 develop 侧
a9f3d2c7e1b4(DEV-34 块 C)形成双头;改为紧随 a9f3d2c7e1b4,合并后全链
e8b2c4f6d9a1 → a9f3d2c7e1b4 → a7c3e1f5b2d8 → b4d8f2a6c9e1 → c9e2b7d4f1a5
单头线性。
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a7c3e1f5b2d8"
down_revision: Union[str, None] = "a9f3d2c7e1b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scn_task_template_trigger",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "template_id",
            sa.String(36),
            sa.ForeignKey(
                "scn_task_template.id",
                name=op.f("fk_scn_task_template_trigger_template_id_scn_task_template"),
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("cron_expr", sa.String(64), nullable=True),
        sa.Column("weekdays", postgresql.JSON(), nullable=True),
        sa.Column("day_of_month", sa.Integer(), nullable=True),
        sa.Column("generate_at", sa.Time(), nullable=False, server_default=sa.text("'00:00:00'")),
        sa.Column("starts_on", sa.Date(), nullable=True),
        sa.Column("ends_on", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        op.f("ix_scn_task_template_trigger_template_id"),
        "scn_task_template_trigger",
        ["template_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_scn_task_template_trigger_template_id"),
        table_name="scn_task_template_trigger",
    )
    op.drop_table("scn_task_template_trigger")
