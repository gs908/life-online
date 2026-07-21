"""
账号主体:父母(GUILD_MASTER)与孩子(ADVENTURER)共享一张表。

- family_id 必填,所有业务数据按家庭隔离
- 业务字段(level/xp/time_coin)放在 sys_child 中,本表只放登录/身份信息
- 与 sys_channel_wechat 一对多
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import UserRole

if TYPE_CHECKING:
    from app.models.sys_family import SysFamily
    from app.models.sys_channel_wechat import SysChannelWechat


class SysAccount(Base, TimestampMixin, UUIDPrimaryKeyMixin):
    __tablename__ = "sys_account"

    family_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("sys_family.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[UserRole] = mapped_column(
        String(32), nullable=False, comment="GUILD_MASTER | ADVENTURER"
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    avatar: Mapped[str] = mapped_column(String(16), nullable=False, default="⚔️")
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="active", comment="active | disabled"
    )

    family: Mapped["SysFamily"] = relationship(back_populates="accounts", lazy="noload")
    channel_wechats: Mapped[list["SysChannelWechat"]] = relationship(
        back_populates="account", cascade="all, delete-orphan", passive_deletes=True
    )
