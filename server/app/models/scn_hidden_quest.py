"""
隐藏任务池:父母/系统投放的惊喜任务定义。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import HiddenTriggerKind

if TYPE_CHECKING:
    from app.models.scn_task_template import ScnTaskTemplate


class ScnHiddenQuest(Base, TimestampMixin, UUIDPrimaryKeyMixin):
    __tablename__ = "scn_hidden_quest"

    family_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sys_family.id", ondelete="CASCADE"), nullable=False, index=True
    )
    season_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scn_season.id", ondelete="CASCADE"), nullable=False, index=True
    )
    template_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("scn_task_template.id", ondelete="SET NULL"), nullable=True, index=True
    )
    trigger_kind: Mapped[HiddenTriggerKind] = mapped_column(
        String(32), nullable=False, default=HiddenTriggerKind.MANUAL, index=True
    )
    trigger_rule: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    title: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    lore_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    xp_reward: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    time_deposit: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    starts_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    max_claims: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    claimed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("sys_account.id", ondelete="SET NULL"), nullable=True, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)

    template: Mapped["ScnTaskTemplate | None"] = relationship(lazy="noload")
