"""
每日统计快照:按家庭/孩子/日期预聚合看板指标。
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import Date, ForeignKey, Integer, JSON, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.common.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ScnStatsDaily(Base, TimestampMixin, UUIDPrimaryKeyMixin):
    __tablename__ = "scn_stats_daily"
    __table_args__ = (
        UniqueConstraint("family_id", "child_id", "stat_date", name="uq_scn_stats_daily_scope"),
    )

    family_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sys_family.id", ondelete="CASCADE"), nullable=False, index=True
    )
    child_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sys_child.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stat_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    quests_completed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quests_submitted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quests_rejected: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quests_abandoned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_rating: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), nullable=True)
    xp_earned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    time_coins_earned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    time_coins_spent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    minutes_active: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    by_type: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    by_category: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
