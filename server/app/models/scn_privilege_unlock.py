"""
已解锁特权:记录孩子达到等级后解锁的特权。
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.db.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.scn_privilege_template import ScnPrivilegeTemplate


class ScnPrivilegeUnlock(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "scn_privilege_unlock"
    __table_args__ = (
        UniqueConstraint(
            "child_id", "privilege_template_id", "season_id", name="uq_scn_privilege_unlock_scope"
        ),
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
    privilege_template_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scn_privilege_template.id", ondelete="CASCADE"), nullable=False, index=True
    )
    unlocked_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), index=True
    )
    used_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    privilege_template: Mapped["ScnPrivilegeTemplate"] = relationship(lazy="joined")
