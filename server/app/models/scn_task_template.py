"""任务模板:父母/系统定义的可实例化任务规则。

实例化后的执行状态放在 scn_task_instance。
"""
from __future__ import annotations

from datetime import datetime, time
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import PoolPolicy, TaskCategory, TaskType, TimedMode

if TYPE_CHECKING:
    from app.models.scn_season import ScnSeason
    from app.models.scn_task_template_trigger import ScnTaskTemplateTrigger


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

    # ---- docs/12 块 A:限时时间窗 / 实例池 / 废弃审计 ----
    # timed_mode 与字段的完整性由 schema 层校验(创建/更新 422):
    # DEADLINE 需 deadline_time;DURATION 需 start_time + duration_minutes;NONE 三者皆空。
    timed_mode: Mapped[TimedMode] = mapped_column(
        String(16), nullable=False, default=TimedMode.NONE
    )
    deadline_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    start_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pool_policy: Mapped[PoolPolicy] = mapped_column(
        String(24), nullable=False, default=PoolPolicy.REUSE_UNTIL_CONSUMED
    )
    # ---- 押金/XP 输入(DEV-34 块 C 语义,块 A 契约可空) ----
    # 预计耗时(分钟):押金 = 耗时驱动的输入(见 coin_service.resolve_deposit)。
    estimated_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 难度 1-5:只影响 XP(见 xp_service.calculate_difficulty_multiplier),不影响押金。
    # 可空 = 未评星;NULL 时 XP 倍率 1.0,与默认 2 等价(docs/04 口径)。
    difficulty: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="难度 1-5")
    # ---- 废弃审计:deprecated_at 非空表示已停用,生成器跳过 ----
    deprecated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deprecated_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)

    season: Mapped["ScnSeason"] = relationship(back_populates="task_templates", lazy="raise")
    # 模板读接口恒带触发规则,selectin 避免 lazy="raise" 踩雷。
    triggers: Mapped[list["ScnTaskTemplateTrigger"]] = relationship(
        back_populates="template",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
        order_by="ScnTaskTemplateTrigger.created_at",
    )
