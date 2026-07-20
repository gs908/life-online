"""
用户已解锁特权:记录孩子达到等级后解锁的特权。

- privilege_id 指向系统/家庭特权定义
- used_count / last_used_at 记录使用概况,详细流水在 redemption_records
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.db.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.family import Family
    from app.models.privilege import Privilege
    from app.models.user import User


class UserPrivilege(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "user_privileges"
    __table_args__ = (
        UniqueConstraint("user_id", "privilege_id", name="uq_user_privilege_user_privilege"),
    )

    family_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("families.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    privilege_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("privileges.id", ondelete="CASCADE"), nullable=False, index=True
    )
    unlocked_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), index=True
    )
    used_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    family: Mapped["Family"] = relationship(lazy="noload")
    user: Mapped["User"] = relationship(lazy="noload")
    privilege: Mapped["Privilege"] = relationship(lazy="joined")
