"""
特权:孩子达到一定等级解锁的奖励。
- 数据相对静态,可放 seed;后续支持家庭自定义
"""
from __future__ import annotations

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.common.db.base import Base, UUIDPrimaryKeyMixin


class Privilege(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "privileges"

    level_required: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    icon: Mapped[str] = mapped_column(String(16), nullable=False, default="⭐")
