"""sys_upload 加 task_instance_id 列(DEV-30)

上传记录与任务实例建立数据库层关联:除 object_key 路径段外,
sys_upload 可直接按任务检索文件。expand-only:
- 新列可空、带索引,存量行保持 NULL,不做数据迁移(开发验证阶段);
- 上传时携带 task_id 即写入;未携带的行由任务提交(submit_task)回填绑定。

Revision ID: e8b2c4f6d9a1
Revises: c7d1e4a9b3f2
Create Date: 2026-10-11 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e8b2c4f6d9a1"
down_revision: Union[str, None] = "c7d1e4a9b3f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sys_upload",
        sa.Column("task_instance_id", sa.String(36), nullable=True),
    )
    op.create_index(
        op.f("ix_sys_upload_task_instance_id"),
        "sys_upload",
        ["task_instance_id"],
    )
    op.create_foreign_key(
        op.f("fk_sys_upload_task_instance_id_scn_task_instance"),
        "sys_upload",
        "scn_task_instance",
        ["task_instance_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_sys_upload_task_instance_id_scn_task_instance"),
        "sys_upload",
        type_="foreignkey",
    )
    op.drop_index(op.f("ix_sys_upload_task_instance_id"), table_name="sys_upload")
    op.drop_column("sys_upload", "task_instance_id")
