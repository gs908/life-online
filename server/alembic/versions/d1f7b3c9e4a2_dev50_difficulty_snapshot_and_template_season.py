"""DEV-50:实例难度快照列 + 模板赛季解绑

两件事:

1. `scn_task_instance.difficulty` —— 难度**快照**列(docs/15 §12 P2 预告的前置)。
   语义是"生成那一刻模板的难度是多少",不是"覆盖层":审批算 XP 时读实例值,
   因此**后续改模板难度不会移动未结算实例的 XP**(这正是 P2 要防的追溯)。
   可空仅因模板难度本身可空(未评星),快照照抄 NULL。

   **必须回填**:存量实例不回填会全部为 NULL → XP 倍率静默从"模板难度"变成
   1.0,产生一次不可见的 XP 变化。回填用"当前模板难度"作为最佳近似
   (等价于"生成时模板就是现在这个难度");`template_id IS NULL`(模板已硬删)
   的行保持 NULL,无从取值。

2. `scn_task_template.season_id` —— 由 `NOT NULL` + `ON DELETE CASCADE`
   改为可空 + `ON DELETE SET NULL`。口诀是"模板可跨赛季,任务不跨赛季":
   模板存的是与赛季无关的任务实质,赛季只是可选"来源标签";实例侧
   `scn_task_instance.season_id` 保持 `NOT NULL`(绑定生成时的赛季),不动。

   改 CASCADE → SET NULL 是资产保护:`CASCADE` 下 `DELETE /scn/seasons/{id}`
   会连带抹掉该赛季全部模板,而模板是可跨赛季复用的资产。

   `upgrade` 是 expand-only:只放宽约束、只增列,**不改任何既有列的类型**;
   唯一的数据写入是给**新增列**回填(既有的 `season_id` 值一律不动)。

   ⚠️ **`downgrade` 会写既有数据**:要恢复 `season_id NOT NULL`,必须先把
   `season_id IS NULL` 的行回填成"该家庭最早的赛季";该家庭已无任何赛季时
   无法补齐,此时显式报错并整体回滚(PG 的 DDL 在同一事务内)。所以本迁移
   的"可回滚"是有条件的 —— 按本文档判断可回滚性时请把这一条算进去。

Revision ID: d1f7b3c9e4a2
Revises: e2f6a8c4b7d9
Create Date: 2026-10-23 00:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d1f7b3c9e4a2"
down_revision: str | None = "e2f6a8c4b7d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SEASON_FK = "fk_scn_task_template_season_id_scn_season"


def upgrade() -> None:
    # ---- 1. 实例难度快照列 + 回填 ----
    op.add_column(
        "scn_task_instance",
        sa.Column(
            "difficulty",
            sa.Integer(),
            nullable=True,
            comment="难度 1-5 快照(生成时从模板复制);NULL=生成时模板未评星(DEV-50)",
        ),
    )
    # 回填:以"当前模板难度"近似"生成时的模板难度"。不回填会让存量实例的
    # XP 倍率静默由模板难度变为 1.0。
    op.execute(
        """
        UPDATE scn_task_instance AS i
        SET difficulty = t.difficulty
        FROM scn_task_template AS t
        WHERE i.template_id = t.id
        """
    )

    # ---- 2. 模板赛季解绑:CASCADE -> SET NULL,并允许为空 ----
    op.drop_constraint(_SEASON_FK, "scn_task_template", type_="foreignkey")
    op.alter_column(
        "scn_task_template",
        "season_id",
        existing_type=sa.String(length=36),
        nullable=True,
    )
    op.create_foreign_key(
        _SEASON_FK,
        "scn_task_template",
        "scn_season",
        ["season_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    # 回滚前先把空值补齐(否则 NOT NULL 无法建立):取该家庭最早的赛季兜底。
    op.execute(
        """
        UPDATE scn_task_template AS t
        SET season_id = (
            SELECT s.id FROM scn_season AS s
            WHERE s.family_id = t.family_id
            ORDER BY s.created_at
            LIMIT 1
        )
        WHERE t.season_id IS NULL
        """
    )
    # 该家庭已经一个赛季都不剩时无从补齐。**显式失败**而不是静默丢数据:整个
    # downgrade 在同一事务里,抛错即整体回滚,不会留下半成品 schema。
    bind = op.get_bind()
    orphan = bind.execute(
        sa.text("SELECT count(*) FROM scn_task_template WHERE season_id IS NULL")
    ).scalar_one()
    if orphan:
        raise RuntimeError(
            f"有 {orphan} 条任务模板没有可回填的赛季(其所属家庭已无任何赛季),"
            "无法恢复 season_id 的 NOT NULL 约束。请先为这些家庭补建赛季,"
            "或手工处置这些模板后再重试 downgrade。"
        )
    op.drop_constraint(_SEASON_FK, "scn_task_template", type_="foreignkey")
    op.alter_column(
        "scn_task_template",
        "season_id",
        existing_type=sa.String(length=36),
        nullable=False,
    )
    op.create_foreign_key(
        _SEASON_FK,
        "scn_task_template",
        "scn_season",
        ["season_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_column("scn_task_instance", "difficulty")