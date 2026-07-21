"""
特权使用记录:孩子使用一次已解锁特权时记一条。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.common.db.base import Base, UUIDPrimaryKeyMixin


class ScnPrivilegeUse(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "scn_privilege_use"

    family_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sys_family.id", ondelete="CASCADE"), nullable=False, index=True
    )
    child_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sys_child.id", ondelete="CASCADE"), nullable=False, index=True
    )
    season_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("scn_season.id", ondelete="SET NULL"), nullable=True, index=True
    )
    privilege_template_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("scn_privilege_template.id", ondelete="SET NULL"), nullable=True, index=True
    )
    privilege_title: Mapped[str] = mapped_column(String(64), nullable=False)
    cost: Mapped[str | None] = mapped_column(String(32), nullable=True)
    used_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), index=True
    )
