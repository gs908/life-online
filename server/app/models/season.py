"""
赛季:每个家庭可有多赛季(寒假/暑假/新学期...),
    一段时间内的主题、剧情、任务都属于同一赛季。
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ThemeId

if TYPE_CHECKING:
    from app.models.family import Family
    from app.models.task import Task


class Season(Base, TimestampMixin, UUIDPrimaryKeyMixin):
    __tablename__ = "seasons"

    family_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("families.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    theme_id: Mapped[ThemeId] = mapped_column(String(32), nullable=False, default=ThemeId.DEFAULT)
    narrative_context: Mapped[str] = mapped_column(Text, nullable=False, default="")
    start_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)

    family: Mapped["Family"] = relationship(back_populates="seasons", lazy="noload")
    tasks: Mapped[list["Task"]] = relationship(
        back_populates="season", cascade="all, delete-orphan", passive_deletes=True
    )
