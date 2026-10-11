"""
任务模板:父母/系统定义的可实例化任务规则。

实例化后的执行状态放在 scn_task_instance。
"""
from __future__ import annotations

from datetime import time
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import TaskCategory, TaskType

if TYPE_CHECKING:
    from app.models.scn_season import ScnSeason


class ScnTaskTemplate(Base, TimestampMixin, UUIDPrimaryKeyMixin):
    __tablename__ = "scn_task_template"

    family_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sys_family.id", ondelete="CASCADE"), nullable=False, index=True
    )
    season_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scn_season.id", ondelete="CASCADE"), nullable=False, index=True
    )
    creator_account_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("sys_account.id", ondelete="SET NULL"), nullable=True
    )
    library_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("scn_task_template_library.id", ondelete="SET NULL"), nullable=True, index=True
    )
    target_child_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("sys_child.id", ondelete="SET NULL"), nullable=True, index=True
    )

    category: Mapped[TaskCategory | None] = mapped_column(String(32), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    lore_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    xp_reward: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    type: Mapped[TaskType] = mapped_column(String(32), nullable=False, default=TaskType.DAILY)
    required_start_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    reminder_message: Mapped[str | None] = mapped_column(String(256), nullable=True)
    reminder_minutes_before: Mapped[int] = mapped_column(Integer, nullable=False, default=15)
    time_deposit: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)

    # ---- CHAIN 递进串行(DEV-36 块 F)------------------------------------
    # 同一条链的各步模板共享 chain_key,按 chain_order(1-based)排序;
    # 实例化时 chain_order/chain_total 快照到 scn_task_instance.chain_index/chain_total,
    # 供链末 XP 加成判定。链的投放/顺延/重做池语义属于 DEV-35 的生成器,
    # 本表只承载链的结构定义。
    chain_key: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    chain_order: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    chain_total: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # 递进难度:每步独立配置,"越来越难"由家长按步设置体现
    estimated_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    difficulty: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    season: Mapped["ScnSeason"] = relationship(back_populates="task_templates", lazy="raise")
