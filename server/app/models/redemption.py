"""
特权使用记录:孩子"兑换/使用"一次特权时记一条。
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.db.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.family import Family
    from app.models.user import User


class RedemptionRecord(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "redemption_records"

    family_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("families.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    privilege_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("privileges.id", ondelete="SET NULL"), nullable=True, index=True
    )
    privilege_title: Mapped[str] = mapped_column(String(64), nullable=False)
    cost: Mapped[str | None] = mapped_column(String(32), nullable=True)
    date: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    family: Mapped["Family"] = relationship(back_populates="redemptions", lazy="noload")
    user: Mapped["User"] = relationship(lazy="noload")
