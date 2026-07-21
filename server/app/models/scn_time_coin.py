"""
时间币账户:每个孩子在家庭/赛季上下文下的当前余额。
"""
from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.common.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ScnTimeCoin(Base, TimestampMixin, UUIDPrimaryKeyMixin):
    __tablename__ = "scn_time_coin"
    __table_args__ = (
        UniqueConstraint("family_id", "child_id", "season_id", name="uq_scn_time_coin_scope"),
    )

    family_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sys_family.id", ondelete="CASCADE"), nullable=False, index=True
    )
    child_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sys_child.id", ondelete="CASCADE"), nullable=False, index=True
    )
    season_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("scn_season.id", ondelete="SET NULL"), nullable=True, index=True
    )
    balance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
