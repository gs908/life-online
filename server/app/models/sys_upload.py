"""
上传文件元数据:用于追踪对象存储/本地文件存储中的文件。
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.db.base import Base, UUIDPrimaryKeyMixin
from app.models.enums import UploadPurpose

if TYPE_CHECKING:
    from app.models.sys_account import SysAccount
    from app.models.sys_family import SysFamily


class SysUpload(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "sys_upload"

    family_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sys_family.id", ondelete="CASCADE"), nullable=False, index=True
    )
    uploader_account_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("sys_account.id", ondelete="SET NULL"), nullable=True, index=True
    )
    storage_provider: Mapped[str] = mapped_column(String(16), nullable=False, default="minio")
    bucket: Mapped[str] = mapped_column(String(64), nullable=False)
    object_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    public_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    content_type: Mapped[str] = mapped_column(
        String(64), nullable=False, default="application/octet-stream"
    )
    size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    purpose: Mapped[UploadPurpose] = mapped_column(
        String(32), nullable=False, default=UploadPurpose.OTHER, index=True
    )
    etag: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    family: Mapped["SysFamily"] = relationship(lazy="noload")
    uploader: Mapped["SysAccount | None"] = relationship(lazy="noload")
