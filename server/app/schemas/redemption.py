"""特权使用记录 DTO。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class RedemptionCreate(BaseModel):
    child_id: str | None = None
    user_id: str | None = None
    privilege_template_id: str | None = None
    privilege_id: str | None = None
    privilege_title: str | None = None
    cost: str | None = None


class RedemptionRead(BaseModel):
    id: str
    family_id: str
    child_id: str
    season_id: str | None = None
    privilege_template_id: str | None = None
    privilege_title: str
    cost: str | None
    used_at: datetime

    # 兼容旧前端字段名。
    user_id: str | None = None
    privilege_id: str | None = None
    date: datetime | None = None
