"""scn_task_participant 加 participant_status 列(DEV-40 COOP「部分完成」状态机)

docs/13 定稿版 §3:参与者子状态四态 JOINED / SUBMITTED / DONE / QUIT,
与实例级 status 正交(实例状态机不动)。

- JOINED:已确认加入(= 原 confirmed_at 语义);
- SUBMITTED:本人份额已交付(各参与者各自 submit);
- DONE:家长已确认本人份额(逐人 approve);
- QUIT:中途退出(leave)或部分通过判退(押金按放弃阶梯结算)。

存量行经 server_default 'JOINED' 一次性回填(所有存量参与者都是"已确认加入"
语义,与 confirmed_at 非空一致),无需逐行迁移脚本。

Revision ID: b7e4d9f2a6c1
Revises: d9f4b2e6c1a8
Create Date: 2026-10-12 12:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7e4d9f2a6c1"
down_revision: Union[str, None] = "d9f4b2e6c1a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "scn_task_participant",
        sa.Column(
            "participant_status",
            sa.String(length=16),
            nullable=False,
            server_default="JOINED",
            comment="参与者子状态:JOINED/SUBMITTED/DONE/QUIT(docs/13 定稿版 §3)",
        ),
    )
    # server_default 已让存量行落 'JOINED'(回填);此 UPDATE 是显式留档的幂等兜底,
    # 防御从手工建表/半迁移状态漂移过来的库。
    op.execute(
        "UPDATE scn_task_participant SET participant_status = 'JOINED' "
        "WHERE participant_status IS NULL OR participant_status = ''"
    )


def downgrade() -> None:
    op.drop_column("scn_task_participant", "participant_status")
