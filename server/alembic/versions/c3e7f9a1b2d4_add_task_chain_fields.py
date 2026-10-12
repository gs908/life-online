"""任务链式字段(DEV-36 块 F: CHAIN 递进串行)

expand-only:
- scn_task_template 加 chain_key/chain_order/chain_total;
- scn_task_instance 加 chain_index/chain_total;
- 全部带默认值,存量行不受影响,不做数据迁移(开发验证阶段)。

estimated_minutes/difficulty 已由 develop 侧迁移(DEV-34 块 C 的 a9f3d2c7e1b4
+ 块 A 的 b4d8f2a6c9e1 放宽可空)建列,本迁移不再重复 add_column。

链说明(DEV-41 集成):down_revision 原为 e8b2c4f6d9a1,与 develop 侧
a9f3d2c7e1b4 及块 A 链(a7c3e1f5b2d8 → b4d8f2a6c9e1 → c9e2b7d4f1a5)形成
多头;改为紧随 c9e2b7d4f1a5,合并后全链
e8b2c4f6d9a1 → a9f3d2c7e1b4 → a7c3e1f5b2d8 → b4d8f2a6c9e1 → c9e2b7d4f1a5
→ c3e7f9a1b2d4 → d5f8e2b4c6a7 单头线性。

Revision ID: c3e7f9a1b2d4
Revises: c9e2b7d4f1a5
Create Date: 2026-10-12 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3e7f9a1b2d4"
down_revision: Union[str, None] = "c9e2b7d4f1a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("scn_task_template", sa.Column("chain_key", sa.String(64), nullable=True))
    op.add_column("scn_task_template", sa.Column("chain_order", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("scn_task_template", sa.Column("chain_total", sa.Integer(), nullable=False, server_default="1"))
    # estimated_minutes/difficulty 由 develop 侧迁移建列,不重复 add(见模块 docstring)
    op.create_index(op.f("ix_scn_task_template_chain_key"), "scn_task_template", ["chain_key"])

    op.add_column("scn_task_instance", sa.Column("chain_index", sa.Integer(), nullable=True))
    op.add_column("scn_task_instance", sa.Column("chain_total", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("scn_task_instance", "chain_total")
    op.drop_column("scn_task_instance", "chain_index")

    op.drop_index(op.f("ix_scn_task_template_chain_key"), table_name="scn_task_template")
    op.drop_column("scn_task_template", "chain_total")
    op.drop_column("scn_task_template", "chain_order")
    op.drop_column("scn_task_template", "chain_key")
