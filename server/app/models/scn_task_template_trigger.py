"""任务模板触发规则:一个模板可挂多条,任一命中即视为当日到期生成。

docs/12 块 A。字段按 kind 取用:
- DAILY   : 仅 generate_at 生效
- WEEKDAYS: weekdays(0=周一..6=周日)
- MONTHLY : day_of_month(月末不足取当月最后一天)
- CRON    : cron_expr(5 段,家庭本地时区 Asia/Shanghai)
- ONCE    : starts_on 当天生成一次
"""
from __future__ import annotations

from datetime import date, time
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Integer,
    JSON,
    String,
    Time,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import TriggerKind

if TYPE_CHECKING:
    from app.models.scn_task_template import ScnTaskTemplate


class ScnTaskTemplateTrigger(Base, TimestampMixin, UUIDPrimaryKeyMixin):
    __tablename__ = "scn_task_template_trigger"

    template_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("scn_task_template.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[TriggerKind] = mapped_column(String(16), nullable=False)
    cron_expr: Mapped[str | None] = mapped_column(String(64), nullable=True)
    weekdays: Mapped[list[int] | None] = mapped_column(JSON, nullable=True)
    day_of_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    generate_at: Mapped[time] = mapped_column(Time, nullable=False, default=time(0, 0))
    starts_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    ends_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # 模板读接口恒带触发规则,selectin 避免 lazy="raise" 踩雷。
    template: Mapped["ScnTaskTemplate"] = relationship(
        back_populates="triggers", lazy="raise"
    )
