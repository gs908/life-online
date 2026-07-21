"""
动态主题:家庭可扩展的主题样式配置。

- family_id 为空表示系统预置主题
- tokens / css_vars 使用 JSON 保存可扩展样式变量
- scene_prompt 记录用户预设场景,便于后续 AI 再生成/迭代
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import Boolean, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.common.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ScnThemeStyle(Base, TimestampMixin, UUIDPrimaryKeyMixin):
    __tablename__ = "scn_theme_style"

    family_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("sys_family.id", ondelete="CASCADE"), nullable=True, index=True
    )
    season_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("scn_season.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    scene_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    description: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    tokens: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    css_vars: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
