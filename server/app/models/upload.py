"""
上传文件元数据:用于追踪对象存储中的文件(便于清理、统计、URL 生成)。
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.db.base import Base, UUIDPrimaryKeyMixin
from app.models.enums import UploadPurpose

if TYPE_CHECKING:
    from app.models.family import Family
    from app.models.user import User


class Upload(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "uploads"

    family_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("families.id", ondelete="CASCADE"), nullable=False, index=True
    )
    uploader_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    object_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    bucket: Mapped[str] = mapped_column(String(64), nullable=False)
    content_type: Mapped[str] = mapped_column(String(64), nullable=False, default="application/octet-stream")
    size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    purpose: Mapped[UploadPurpose] = mapped_column(
        String(32), nullable=False, default=UploadPurpose.OTHER, index=True
    )
    etag: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(),
    )

    family: Mapped["Family"] = relationship(back_populates="uploads", lazy="noload")
    uploader: Mapped["User | None"] = relationship(lazy="noload")
