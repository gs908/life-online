"""
通知:站内消息与微信模板消息发送记录。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.common.db.base import Base, UUIDPrimaryKeyMixin
from app.models.enums import NotificationChannel, NotificationStatus, NotificationType


class ScnNotification(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "scn_notification"

    family_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sys_family.id", ondelete="CASCADE"), nullable=False, index=True
    )
    recipient_account_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sys_account.id", ondelete="CASCADE"), nullable=False, index=True
    )
    channel: Mapped[NotificationChannel] = mapped_column(
        String(16), nullable=False, default=NotificationChannel.INAPP, index=True
    )
    type: Mapped[NotificationType] = mapped_column(String(32), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[NotificationStatus] = mapped_column(
        String(16), nullable=False, default=NotificationStatus.PENDING, index=True
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    wechat_msg_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), index=True
    )
