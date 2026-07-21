"""时间币业务账本:记录每日配额、任务押金、退款、惩罚与人工调整。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.common.db.base import Base, UUIDPrimaryKeyMixin
from app.models.enums import CoinTransactionType


class ScnTimeCoinLog(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "scn_time_coin_log"

    family_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sys_family.id", ondelete="CASCADE"), nullable=False, index=True
    )
    child_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sys_child.id", ondelete="CASCADE"), nullable=False, index=True
    )
    season_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("scn_season.id", ondelete="SET NULL"), nullable=True, index=True
    )
    task_instance_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("scn_task_instance.id", ondelete="SET NULL"), nullable=True, index=True
    )
    type: Mapped[CoinTransactionType] = mapped_column(String(32), nullable=False, index=True)
    amount: Mapped[int] = mapped_column(Integer, nullable=False, comment="正数表示增加,负数表示扣减")
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), index=True
    )
