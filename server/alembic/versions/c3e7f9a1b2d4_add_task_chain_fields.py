"""任务链式字段(DEV-36 块 F: CHAIN 递进串行)

expand-only:
- scn_task_template 加 chain_key/chain_order/chain_total/estimated_minutes/difficulty;
- scn_task_instance 加 chain_index/chain_total;
- 全部带默认值,存量行不受影响,不做数据迁移(开发验证阶段)。

Revision ID: c3e7f9a1b2d4
Revises: e8b2c4f6d9a1
Create Date: 2026-10-12 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3e7f9a1b2d4"
down_revision: Union[str, None] = "e8b2c4f6d9a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("scn_task_template", sa.Column("chain_key", sa.String(64), nullable=True))
    op.add_column("scn_task_template", sa.Column("chain_order", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("scn_task_template", sa.Column("chain_total", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("scn_task_template", sa.Column("estimated_minutes", sa.Integer(), nullable=True))
    op.add_column("scn_task_template", sa.Column("difficulty", sa.Integer(), nullable=False, server_default="1"))
    op.create_index(op.f("ix_scn_task_template_chain_key"), "scn_task_template", ["chain_key"])

    op.add_column("scn_task_instance", sa.Column("chain_index", sa.Integer(), nullable=True))
    op.add_column("scn_task_instance", sa.Column("chain_total", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("scn_task_instance", "chain_total")
    op.drop_column("scn_task_instance", "chain_index")

    op.drop_index(op.f("ix_scn_task_template_chain_key"), table_name="scn_task_template")
    op.drop_column("scn_task_template", "difficulty")
    op.drop_column("scn_task_template", "estimated_minutes")
    op.drop_column("scn_task_template", "chain_total")
    op.drop_column("scn_task_template", "chain_order")
    op.drop_column("scn_task_template", "chain_key")
