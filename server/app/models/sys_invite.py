"""
家庭邀请码:父母可生成短码邀请配偶/孩子加入。
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.db.base import Base, UUIDPrimaryKeyMixin
from app.models.enums import InviteRole

if TYPE_CHECKING:
    from app.models.sys_account import SysAccount
    from app.models.sys_family import SysFamily


class SysInvite(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "sys_invite"

    family_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("sys_family.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code: Mapped[str] = mapped_column(String(16), nullable=False, unique=True, index=True)
    role: Mapped[InviteRole] = mapped_column(
        String(32), nullable=False, default=InviteRole.ADVENTURER
    )
    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("sys_account.id", ondelete="SET NULL"), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    used_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("sys_account.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    family: Mapped["SysFamily"] = relationship(back_populates="invites", lazy="noload")
    creator: Mapped["SysAccount | None"] = relationship(
        foreign_keys=[created_by], lazy="noload"
    )
    consumer: Mapped["SysAccount | None"] = relationship(
        foreign_keys=[used_by], lazy="noload"
    )
