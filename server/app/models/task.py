"""
任务:核心业务实体。

- target_user_id: 指定接取的孩子(NULL = 任意孩子可接)
- assignee_id: 当前接取人(IN_PROGRESS 时)
- type / status 用枚举字符串存储
- 状态机在 services/task_service.py 中管控
"""
from __future__ import annotations

from datetime import datetime, time
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import TaskStatus, TaskType

if TYPE_CHECKING:
    from app.models.family import Family
    from app.models.season import Season
    from app.models.user import User


class Task(Base, TimestampMixin, UUIDPrimaryKeyMixin):
    __tablename__ = "tasks"

    family_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("families.id", ondelete="CASCADE"), nullable=False, index=True
    )
    season_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # 任务创建者(父母)
    creator_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # 目标接取者(NULL = 任意)
    target_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # 当前接取人
    assignee_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    title: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    lore_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    xp_reward: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    type: Mapped[TaskType] = mapped_column(String(32), nullable=False, default=TaskType.DAILY)
    status: Mapped[TaskStatus] = mapped_column(
        String(32), nullable=False, default=TaskStatus.AVAILABLE, index=True
    )

    deadline: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    required_start_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    proof_object_key: Mapped[str | None] = mapped_column(
        String(512), nullable=True, comment="对象存储 key,完整 URL 通过 storage client 生成"
    )
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="1-5 星")

    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    reminder_message: Mapped[str | None] = mapped_column(String(256), nullable=True)
    reminder_minutes_before: Mapped[int] = mapped_column(Integer, nullable=False, default=15)
    time_deposit: Mapped[int] = mapped_column(Integer, nullable=False, default=10)

    family: Mapped["Family"] = relationship(lazy="noload")
    season: Mapped["Season"] = relationship(back_populates="tasks", lazy="noload")
    creator: Mapped["User | None"] = relationship(foreign_keys=[creator_id], lazy="noload")
    assignee: Mapped["User | None"] = relationship(
        foreign_keys=[assignee_id], back_populates="assigned_tasks", lazy="noload"
    )
