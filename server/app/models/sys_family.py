"""
家庭:业务数据的顶层隔离单元。

- 邀请、用户、赛季、任务、特权等都属于某个家庭
- owner_id 逻辑引用,不建外键以便后续清理
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.sys_account import SysAccount
    from app.models.sys_invite import SysInvite


class SysFamily(Base, TimestampMixin, UUIDPrimaryKeyMixin):
    __tablename__ = "sys_family"

    name: Mapped[str] = mapped_column(String(64), nullable=False)
    owner_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, comment="创建者 sys_account.id,逻辑引用,不建外键以允许清理"
    )

    accounts: Mapped[list["SysAccount"]] = relationship(
        back_populates="family", cascade="save-update", passive_deletes=True
    )
    invites: Mapped[list["SysInvite"]] = relationship(
        back_populates="family", cascade="all, delete-orphan", passive_deletes=True
    )
