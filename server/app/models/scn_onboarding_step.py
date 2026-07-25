"""
新手引导步骤:一条 onboarding path 下的具体任务节点。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.scn_onboarding_path import ScnOnboardingPath
    from app.models.scn_task_template import ScnTaskTemplate


class ScnOnboardingStep(Base, TimestampMixin, UUIDPrimaryKeyMixin):
    __tablename__ = "scn_onboarding_step"
    __table_args__ = (
        UniqueConstraint("path_id", "sort_order", name="uq_scn_onboarding_step_order"),
    )

    path_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scn_onboarding_path.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    template_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("scn_task_template.id", ondelete="SET NULL"), nullable=True, index=True
    )
    unlocks_after: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("scn_onboarding_step.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reward_xp: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reward_coin: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    path: Mapped["ScnOnboardingPath"] = relationship(back_populates="steps", lazy="noload")
    template: Mapped["ScnTaskTemplate | None"] = relationship(lazy="noload")
