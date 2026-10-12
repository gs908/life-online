"""COOP 任务参与者(DEV-36 块 F)。

- 主接取人由 `scn_task_instance.assignee_child_id` 指向;本表同时登记他(OWNER),
  保证"链上所有人"只看一张表。
- 多孩子协作:除 OWNER 外的参与者角色为 MEMBER。
- 亲子协作:家长以 PARENT 角色参与,`child_id` 为空——家长没有时间币/XP 账户,
  不参与押金均摊、不获得 XP(见 docs/04 §4)。
- 押金/XP 的均摊规则在 `app.services.coop_service`,本表只落每人份额与结算结果,
  便于审计与"部分完成"状态机(设计草案见 docs/13)后续在此之上扩展。
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import TaskParticipantRole, TaskParticipantStatus

if TYPE_CHECKING:
    from app.models.scn_task_instance import ScnTaskInstance


class ScnTaskParticipant(Base, TimestampMixin, UUIDPrimaryKeyMixin):
    __tablename__ = "scn_task_participant"
    __table_args__ = (
        UniqueConstraint("task_instance_id", "account_id", name="uq_scn_task_participant_task_account"),
    )

    task_instance_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("scn_task_instance.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 参与者一律对应一个账号(孩子或家长),按账号去重防止重复加入
    account_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sys_account.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # 家长参与者(PARENT)没有 sys_child 行,此列为空
    child_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("sys_child.id", ondelete="SET NULL"), nullable=True, index=True
    )

    role: Mapped[str] = mapped_column(
        String(32), nullable=False, default=TaskParticipantRole.MEMBER
    )
    # 参与者子状态(docs/13 定稿版 §3):JOINED/SUBMITTED/DONE/QUIT,与实例状态正交
    participant_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=TaskParticipantStatus.JOINED,
        server_default="JOINED",
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # 均摊后的押金份额(家长参与者恒为 0);审批/放弃/过期按此结算
    deposit_share: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    xp_awarded: Mapped[int | None] = mapped_column(Integer, nullable=True)

    task_instance: Mapped["ScnTaskInstance"] = relationship(
        back_populates="participants", lazy="raise"
    )
