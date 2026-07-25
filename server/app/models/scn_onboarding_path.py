"""
新手引导路径:孩子进入正式 Quest Board 前的任务线。
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.scn_onboarding_step import ScnOnboardingStep


class ScnOnboardingPath(Base, TimestampMixin, UUIDPrimaryKeyMixin):
    __tablename__ = "scn_onboarding_path"

    family_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("sys_family.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    starts_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)

    steps: Mapped[list["ScnOnboardingStep"]] = relationship(
        back_populates="path",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ScnOnboardingStep.sort_order",
    )
