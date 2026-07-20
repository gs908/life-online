"""
时间币配置例外:按星期几(day_of_week: 0=周日, 1=周一, ...)覆盖默认配额。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.db.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.time_config import TimeConfig


class TimeConfigException(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "time_config_exceptions"
    __table_args__ = (
        UniqueConstraint("time_config_id", "day_of_week", name="uq_tce_config_day"),
    )

    time_config_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("time_configs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False, comment="0=Sun, 6=Sat")
    coin_amount: Mapped[int] = mapped_column(Integer, nullable=False)

    time_config: Mapped["TimeConfig"] = relationship(back_populates="exceptions", lazy="noload")
