"""
任务模板库:平台/家庭预置的可一键套用任务定义。
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import Boolean, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.common.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import TaskCategory, TaskType


class ScnTaskTemplateLibrary(Base, TimestampMixin, UUIDPrimaryKeyMixin):
    __tablename__ = "scn_task_template_library"

    family_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("sys_family.id", ondelete="CASCADE"), nullable=True, index=True
    )
    category: Mapped[TaskCategory] = mapped_column(
        String(32), nullable=False, default=TaskCategory.OTHER, index=True
    )
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    title: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    suggested_xp: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    suggested_time_deposit: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    suggested_type: Mapped[TaskType] = mapped_column(String(32), nullable=False, default=TaskType.DAILY)
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
