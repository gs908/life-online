"""sys_upload 加 deleted_at 列(DEV-37 / DEV-33 块 E)

sys_upload 退为通用文件台账后,清理链路(A7.3,后续任务)需要软删标记:
- `DELETE /scn/task-proofs/{id}` 只软删 scn_task_proof 行,台账行不动;
- 台账层的软删由本列承载(行还在、物理对象还在,但不再参与业务读取),
  180 天后的定时真删以 `deleted_at` 为准。

expand-only:新列可空、带索引,存量行保持 NULL,不做数据回填。

Revision ID: d9f4b2e6c1a8
Revises: c3e7a1f5b8d2
Create Date: 2026-10-12 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d9f4b2e6c1a8"
down_revision: Union[str, None] = "c3e7a1f5b8d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sys_upload",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        op.f("ix_sys_upload_deleted_at"),
        "sys_upload",
        ["deleted_at"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_sys_upload_deleted_at"), table_name="sys_upload")
    op.drop_column("sys_upload", "deleted_at")
