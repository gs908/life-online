"""任务内容生成列(docs/15 §5,DEV-49)

- scn_task_template: content_mode(VARCHAR(16) 非空,默认 STATIC)、content_brief(TEXT 可空)
- scn_task_instance: content_source(VARCHAR(16) 非空,默认 TEMPLATE)、generation_meta(JSON 可空)

expand-only:全部新列只增不改,存量行经 server_default 一次性回填默认值
(STATIC / TEMPLATE),不触碰任何既有列与数据。

Revision ID: e2f6a8c4b7d9
Revises: b7e4d9f2a6c1
Create Date: 2026-10-18 12:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e2f6a8c4b7d9"
down_revision: str | None = "b7e4d9f2a6c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "scn_task_template",
        sa.Column(
            "content_mode",
            sa.String(length=16),
            nullable=False,
            server_default="STATIC",
            comment="内容生成模式:STATIC/LLM(docs/15 R1)",
        ),
    )
    op.add_column(
        "scn_task_template",
        sa.Column(
            "content_brief",
            sa.Text(),
            nullable=True,
            comment="任务要点:LLM 叙事生成的输入;空则生成器回落用 description(docs/15 R2)",
        ),
    )
    op.add_column(
        "scn_task_instance",
        sa.Column(
            "content_source",
            sa.String(length=16),
            nullable=False,
            server_default="TEMPLATE",
            comment="叙事来源:TEMPLATE/LLM/FALLBACK(docs/15 R3)",
        ),
    )
    op.add_column(
        "scn_task_instance",
        sa.Column(
            "generation_meta",
            sa.JSON(),
            nullable=True,
            comment="生成元数据(内部数据,不出 API):模型名/提示词哈希/token 数/耗时/错误类名(docs/15 R4)",
        ),
    )


def downgrade() -> None:
    op.drop_column("scn_task_instance", "generation_meta")
    op.drop_column("scn_task_instance", "content_source")
    op.drop_column("scn_task_template", "content_brief")
    op.drop_column("scn_task_template", "content_mode")
