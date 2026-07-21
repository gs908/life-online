"""
时间币配置:每个家庭独立一份默认日配额配置。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.scn_time_config_exception import ScnTimeConfigException


class ScnTimeConfig(Base, TimestampMixin, UUIDPrimaryKeyMixin):
    __tablename__ = "scn_time_config"

    family_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("sys_family.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    default_daily_allowance: Mapped[int] = mapped_column(Integer, nullable=False, default=100)

    exceptions: Mapped[list["ScnTimeConfigException"]] = relationship(
        back_populates="time_config",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ScnTimeConfigException.day_of_week",
    )
