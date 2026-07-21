"""
特权模板:达到一定等级后可解锁的奖励定义。
"""
from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.common.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ScnPrivilegeTemplate(Base, TimestampMixin, UUIDPrimaryKeyMixin):
    __tablename__ = "scn_privilege_template"

    family_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("sys_family.id", ondelete="CASCADE"), nullable=True, index=True
    )
    season_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("scn_season.id", ondelete="SET NULL"), nullable=True, index=True
    )
    level_required: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    icon: Mapped[str] = mapped_column(String(16), nullable=False, default="⭐")
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
