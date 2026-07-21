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
from app.models.enums import TaskType

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
    target_child_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("sys_child.id", ondelete="SET NULL"), nullable=True, index=True
    )

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

    season: Mapped["ScnSeason"] = relationship(back_populates="task_templates", lazy="noload")
