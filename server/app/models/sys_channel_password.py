"""
密码渠道绑定:一个 sys_account 至多一条密码登录凭据(与 sys_channel_wechat 并列)。

- username 全表唯一(统一小写存储,实现大小写不敏感登录)
- password_hash 存 scrypt 摘要(见 app/common/security/password.py),不落明文
- 微信注册的账号可以后续补设密码(同一账号多登录渠道并存),反之亦然
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.sys_account import SysAccount


class SysChannelPassword(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "sys_channel_password"

    account_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("sys_account.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    username: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)

    account: Mapped["SysAccount"] = relationship(
        back_populates="channel_password", lazy="noload", uselist=False
    )
