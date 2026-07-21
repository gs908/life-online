"""
孩子档案:ADVENTURER 业务侧资料。

- 业务字段(level/xp/time_coin_balance/daily_abandon_count/current_season)放这里
- account_id 关联到 sys_account
- 家庭归属冗余存放,方便按家庭查询
"""
from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.sys_account import SysAccount
    from app.models.sys_family import SysFamily


class SysChild(Base, TimestampMixin, UUIDPrimaryKeyMixin):
    __tablename__ = "sys_child"

    account_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("sys_account.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    family_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("sys_family.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    display_name: Mapped[str] = mapped_column(String(64), nullable=False)
    avatar: Mapped[str] = mapped_column(String(16), nullable=False, default="🧒")

    level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    xp: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    time_coin_balance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    daily_abandon_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_login_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    current_season_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    account: Mapped["SysAccount"] = relationship(lazy="joined")
    family: Mapped["SysFamily"] = relationship(lazy="noload")
