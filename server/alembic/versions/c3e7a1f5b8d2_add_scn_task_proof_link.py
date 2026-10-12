"""启用 scn_task_proof 证据表所需的索引(DEV-37 / DEV-33 块 E)

scn_task_proof 表结构在 d4a5b93011d5 已建齐(family/task/kind/object_key 唯一
等),本迁移补上"按任务读取证据列表"的组合索引:

- `ix_scn_task_proof_task_instance_id_deleted_at (task_instance_id, deleted_at)`
  服务 `GET /scn/task-instances/{id}/proofs` 与 TaskRead.proofs 的
  `WHERE task_instance_id = ? AND deleted_at IS NULL` 查询;
  原单列 task_instance_id 索引保留(外键/等值查询仍可用)。

刻意**不建** scn_task_proof.object_key -> sys_upload.object_key 的物理外键:
按 docs/12 §5.2 / D5,两表是"逻辑引用"关系 —— sys_upload 退为通用文件台账,
后续清理任务(A7.3: 软删 + 保留 180 天真删)要能独立删除台账行,
物理外键会把真删流程锁死在证据表上。

Revision ID: c3e7a1f5b8d2
Revises: a9f3d2c7e1b4
Create Date: 2026-10-12 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3e7a1f5b8d2"
down_revision: Union[str, None] = "a9f3d2c7e1b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        op.f("ix_scn_task_proof_task_instance_id_deleted_at"),
        "scn_task_proof",
        ["task_instance_id", "deleted_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_scn_task_proof_task_instance_id_deleted_at"),
        table_name="scn_task_proof",
    )
