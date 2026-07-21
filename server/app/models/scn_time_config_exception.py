"""
时间币配置例外:按星期几(day_of_week: 0=周日, 1=周一, ...)覆盖默认配额。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.db.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.scn_time_config import ScnTimeConfig


class ScnTimeConfigException(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "scn_time_config_exception"
    __table_args__ = (
        UniqueConstraint("time_config_id", "day_of_week", name="uq_scn_time_config_exception_day"),
    )

    time_config_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scn_time_config.id", ondelete="CASCADE"), nullable=False, index=True
    )
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False, comment="0=Sun, 6=Sat")
    coin_amount: Mapped[int] = mapped_column(Integer, nullable=False)

    time_config: Mapped["ScnTimeConfig"] = relationship(back_populates="exceptions", lazy="noload")
