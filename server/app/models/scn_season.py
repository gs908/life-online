"""
游戏赛季:一段时间内的主题、剧情、任务和特权解锁上下文。
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ThemeId

if TYPE_CHECKING:
    from app.models.scn_task_instance import ScnTaskInstance
    from app.models.scn_task_template import ScnTaskTemplate
    from app.models.sys_family import SysFamily


class ScnSeason(Base, TimestampMixin, UUIDPrimaryKeyMixin):
    __tablename__ = "scn_season"
    __table_args__ = (
        # 部分唯一索引:同一家庭同时只能有一个激活赛季,在数据库层面兜底,
        # 而不仅依赖服务层"先下线旧赛季再插入/激活新赛季"这一非原子的两步操作。
        Index("ux_scn_season_active_per_family", "family_id", unique=True, postgresql_where=text("is_active")),
    )

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
