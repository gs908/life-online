"""
微信渠道绑定:一个 sys_account 可绑定多个微信账号(扫码 + 小程序)。

- unionid 用于跨应用识别同一用户(开放平台下 unionid 唯一)
- openid 在同一开放平台/小程序下唯一
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.db.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.sys_account import SysAccount


class SysChannelWechat(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "sys_channel_wechat"

    account_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("sys_account.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    openid: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    unionid: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    nickname: Mapped[str | None] = mapped_column(String(64), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    access_token: Mapped[str | None] = mapped_column(String(512), nullable=True)
    refresh_token: Mapped[str | None] = mapped_column(String(512), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    account: Mapped["SysAccount"] = relationship(back_populates="channel_wechats", lazy="joined")
