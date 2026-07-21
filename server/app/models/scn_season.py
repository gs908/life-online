"""
游戏赛季:一段时间内的主题、剧情、任务和特权解锁上下文。
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ThemeId

if TYPE_CHECKING:
    from app.models.scn_task_instance import ScnTaskInstance
    from app.models.scn_task_template import ScnTaskTemplate
    from app.models.sys_family import SysFamily


class ScnSeason(Base, TimestampMixin, UUIDPrimaryKeyMixin):
    __tablename__ = "scn_season"

    family_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sys_family.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    theme_id: Mapped[ThemeId] = mapped_column(String(32), nullable=False, default=ThemeId.DEFAULT)
    narrative_context: Mapped[str] = mapped_column(Text, nullable=False, default="")
    start_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)

    family: Mapped["SysFamily"] = relationship(lazy="noload")
    task_templates: Mapped[list["ScnTaskTemplate"]] = relationship(
        back_populates="season", cascade="all, delete-orphan", passive_deletes=True
    )
    task_instances: Mapped[list["ScnTaskInstance"]] = relationship(
        back_populates="season", cascade="all, delete-orphan", passive_deletes=True
    )
