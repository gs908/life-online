"""COOP 任务参与者表(DEV-36 块 F: COOP 多参与者协作)

独立于链式字段迁移(issue 约定:参与者表另出迁移,便于"部分完成"
状态机设计定稿后按需追加/调整列)。纯新增表,不影响存量数据。

Revision ID: d5f8e2b4c6a7
Revises: c3e7f9a1b2d4
Create Date: 2026-10-12 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d5f8e2b4c6a7"
down_revision: Union[str, None] = "c3e7f9a1b2d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scn_task_participant",
        sa.Column("task_instance_id", sa.String(36), nullable=False),
        sa.Column("account_id", sa.String(36), nullable=False),
        sa.Column("child_id", sa.String(36), nullable=True),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deposit_share", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("xp_awarded", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", sa.String(36), nullable=False),
        sa.ForeignKeyConstraint(
            ["task_instance_id"], ["scn_task_instance.id"],
            name=op.f("fk_scn_task_participant_task_instance_id_scn_task_instance"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"], ["sys_account.id"],
            name=op.f("fk_scn_task_participant_account_id_sys_account"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["child_id"], ["sys_child.id"],
            name=op.f("fk_scn_task_participant_child_id_sys_child"), ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scn_task_participant")),
        sa.UniqueConstraint(
            "task_instance_id", "account_id",
            name="uq_scn_task_participant_task_account",
        ),
    )
    op.create_index(op.f("ix_scn_task_participant_task_instance_id"), "scn_task_participant", ["task_instance_id"])
    op.create_index(op.f("ix_scn_task_participant_account_id"), "scn_task_participant", ["account_id"])
    op.create_index(op.f("ix_scn_task_participant_child_id"), "scn_task_participant", ["child_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_scn_task_participant_child_id"), table_name="scn_task_participant")
    op.drop_index(op.f("ix_scn_task_participant_account_id"), table_name="scn_task_participant")
    op.drop_index(op.f("ix_scn_task_participant_task_instance_id"), table_name="scn_task_participant")
    op.drop_table("scn_task_participant")
