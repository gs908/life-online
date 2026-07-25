"""
任务证据:任务提交时上传的图片/视频/音频等凭证。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.common.db.base import Base, UUIDPrimaryKeyMixin
from app.models.enums import ProofKind


class ScnTaskProof(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "scn_task_proof"

    family_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sys_family.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_instance_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scn_task_instance.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[ProofKind] = mapped_column(String(16), nullable=False, index=True)
    object_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content_type: Mapped[str] = mapped_column(String(64), nullable=False, default="application/octet-stream")
    uploaded_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("sys_account.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), index=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
