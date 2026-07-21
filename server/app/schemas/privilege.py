"""特权 DTO。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class PrivilegeRead(BaseModel):
    id: str
    family_id: str | None = None
    season_id: str | None = None
    level_required: int
    title: str
    description: str
    icon: str
    is_system: bool = False
    is_active: bool = True


class UserPrivilegeUseRequest(BaseModel):
    child_id: str | None = None
    user_id: str | None = None
    privilege_template_id: str | None = None
    privilege_id: str | None = None
    cost: str | None = None


class UserPrivilegeRead(BaseModel):
    id: str
    family_id: str
    child_id: str
    season_id: str | None = None
    privilege_template_id: str
    privilege: PrivilegeRead
    unlocked_at: datetime
    used_count: int
    last_used_at: datetime | None = None

    # 兼容旧前端字段名。
    user_id: str | None = None
