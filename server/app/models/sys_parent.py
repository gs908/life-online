"""
家长档案:GUILD_MASTER 业务侧资料。

- account_id 关联到 sys_account,作为登录主体
- family_id 冗余存放,方便按家庭查询
- 通知/偏好等家长专属设置放这里
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.sys_account import SysAccount
    from app.models.sys_family import SysFamily


class SysParent(Base, TimestampMixin, UUIDPrimaryKeyMixin):
    __tablename__ = "sys_parent"

    account_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("sys_account.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    family_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("sys_family.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    display_name: Mapped[str] = mapped_column(String(64), nullable=False)
    notify_settings: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    account: Mapped["SysAccount"] = relationship(lazy="joined")
    family: Mapped["SysFamily"] = relationship(lazy="noload")
