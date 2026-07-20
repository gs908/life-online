"""
时间币配置:每个家庭独立一份(默认日配额 + 每日例外,如周末翻倍)。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.family import Family
    from app.models.time_config_exception import TimeConfigException


class TimeConfig(Base, TimestampMixin, UUIDPrimaryKeyMixin):
    __tablename__ = "time_configs"

    family_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("families.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    default_daily_allowance: Mapped[int] = mapped_column(Integer, nullable=False, default=100)

    family: Mapped["Family"] = relationship(back_populates="time_config", lazy="noload")
    exceptions: Mapped[list["TimeConfigException"]] = relationship(
        back_populates="time_config",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="TimeConfigException.day_of_week",
    )
