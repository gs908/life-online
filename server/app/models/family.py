"""
家庭:所有业务数据的顶层隔离单元。

每个用户、赛季、任务、特权使用记录都属于某个家庭。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.family_invite import FamilyInvite
    from app.models.redemption import RedemptionRecord
    from app.models.season import Season
    from app.models.time_config import TimeConfig
    from app.models.upload import Upload
    from app.models.user import User


class Family(Base, TimestampMixin, UUIDPrimaryKeyMixin):
    __tablename__ = "families"

    name: Mapped[str] = mapped_column(String(64), nullable=False)
    owner_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, comment="创建者 user.id,逻辑引用,不建外键以允许清理"
    )

    members: Mapped[list["User"]] = relationship(
        back_populates="family", cascade="save-update", passive_deletes=True
    )
    seasons: Mapped[list["Season"]] = relationship(
        back_populates="family", cascade="all, delete-orphan", passive_deletes=True
    )
    invites: Mapped[list["FamilyInvite"]] = relationship(
        back_populates="family", cascade="all, delete-orphan", passive_deletes=True
    )
    time_config: Mapped["TimeConfig | None"] = relationship(
        back_populates="family", cascade="all, delete-orphan",
        passive_deletes=True, uselist=False,
    )
    redemptions: Mapped[list["RedemptionRecord"]] = relationship(
        back_populates="family", cascade="all, delete-orphan", passive_deletes=True
    )
    uploads: Mapped[list["Upload"]] = relationship(
        back_populates="family", cascade="save-update", passive_deletes=True
    )
