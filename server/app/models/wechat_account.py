"""
微信账号绑定:支持多 provider 扩展,当前只接微信(扫码 + 小程序)。

unionid 用于跨应用识别同一用户(开放平台下 unionid 唯一);
openid 在同一开放平台/小程序下唯一。
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.db.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User


class WechatAccount(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "wechat_accounts"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # 同一开放平台/小程序下唯一
    openid: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    # 跨应用同一微信用户,可能为空(未绑定开放平台)
    unionid: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    # 区分是扫码登录(open)还是小程序(mp)
    provider: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    nickname: Mapped[str | None] = mapped_column(String(64), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    access_token: Mapped[str | None] = mapped_column(String(512), nullable=True)
    refresh_token: Mapped[str | None] = mapped_column(String(512), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(),
    )

    user: Mapped["User"] = relationship(back_populates="wechat_accounts", lazy="joined")
