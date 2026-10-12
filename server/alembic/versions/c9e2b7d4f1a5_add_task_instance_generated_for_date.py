"""scn_task_instance.generated_for_date + partial unique index(DEV-35 块 A)

实例归属逻辑日:生成器产出实例时锚定"为哪一天生成";
UNIQUE(template_id, generated_for_date) WHERE generated_for_date IS NOT NULL
兜底并发生成(撞库回捞,见 task_generator_service._insert_instance)。
一次性手工任务 generated_for_date 为 NULL,不参与唯一约束。
expand-only:新列可空,存量行保持 NULL。

Revision ID: c9e2b7d4f1a5
Revises: b4d8f2a6c9e1
Create Date: 2026-10-12 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9e2b7d4f1a5"
down_revision: Union[str, None] = "b4d8f2a6c9e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("scn_task_instance", sa.Column("generated_for_date", sa.Date(), nullable=True))
    op.create_index(
        "uq_scn_task_instance_template_generated_for_date",
        "scn_task_instance",
        ["template_id", "generated_for_date"],
        unique=True,
        postgresql_where=sa.text("generated_for_date IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_scn_task_instance_template_generated_for_date",
        table_name="scn_task_instance",
    )
    op.drop_column("scn_task_instance", "generated_for_date")
