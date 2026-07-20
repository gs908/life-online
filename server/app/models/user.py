"""
用户:父母(GUILD_MASTER)与孩子(ADVENTURER)共用一张表,通过 role 区分。

- family_id 必填,实现多孩子/多父母共享家庭
- 与 WechatAccount 一对多
"""
from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import UserRole

if TYPE_CHECKING:
    from app.models.family import Family
    from app.models.task import Task
    from app.models.wechat_account import WechatAccount


class User(Base, TimestampMixin, UUIDPrimaryKeyMixin):
    __tablename__ = "users"

    family_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("families.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[UserRole] = mapped_column(
        String(32), nullable=False, comment="GUILD_MASTER | ADVENTURER"
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    avatar: Mapped[str] = mapped_column(String(16), nullable=False, default="⚔️")

    level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    xp: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    time_coins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    daily_abandon_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_login_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # 孩子特权解锁(以 JSON 字符串存等级列表,简单且兼容;后续迁移到 user_privileges)
    privileges_unlocked: Mapped[str] = mapped_column(
        String(255), nullable=False, default="", comment='JSON 字符串,如 "[1,2,5]"'
    )

    family: Mapped["Family"] = relationship(back_populates="members", lazy="noload")
    wechat_accounts: Mapped[list["WechatAccount"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    assigned_tasks: Mapped[list["Task"]] = relationship(
        back_populates="assignee",
        foreign_keys="Task.assignee_id",
        cascade="save-update",
        passive_deletes=True,
    )
