"""
任务实例:某个任务模板在具体周期/孩子上的执行记录。
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import TaskStatus

if TYPE_CHECKING:
    from app.models.scn_season import ScnSeason
    from app.models.scn_task_template import ScnTaskTemplate


class ScnTaskInstance(Base, TimestampMixin, UUIDPrimaryKeyMixin):
    __tablename__ = "scn_task_instance"

    family_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sys_family.id", ondelete="CASCADE"), nullable=False, index=True
    )
    season_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scn_season.id", ondelete="CASCADE"), nullable=False, index=True
    )
    template_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("scn_task_template.id", ondelete="SET NULL"), nullable=True, index=True
    )
    creator_account_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("sys_account.id", ondelete="SET NULL"), nullable=True
    )
    target_child_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("sys_child.id", ondelete="SET NULL"), nullable=True, index=True
    )
    assignee_child_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("sys_child.id", ondelete="SET NULL"), nullable=True, index=True
    )

    title: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    lore_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    xp_reward: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    status: Mapped[TaskStatus] = mapped_column(
        String(32), nullable=False, default=TaskStatus.AVAILABLE, index=True
    )
    deadline: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expire_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    proof_object_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="1-5 星")
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    xp_awarded: Mapped[int | None] = mapped_column(Integer, nullable=True)
    coin_delta: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    abandon_count_at_submit: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    time_deposit: Mapped[int] = mapped_column(Integer, nullable=False, default=10)

    season: Mapped["ScnSeason"] = relationship(back_populates="task_instances", lazy="noload")
    template: Mapped["ScnTaskTemplate | None"] = relationship(lazy="noload")
