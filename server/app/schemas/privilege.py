"""特权 DTO。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class PrivilegeRead(BaseModel):
    id: str
    level_required: int
    title: str
    description: str
    icon: str


class UserPrivilegeUseRequest(BaseModel):
    user_id: str
    privilege_id: str
    cost: str | None = None


class UserPrivilegeRead(BaseModel):
    id: str
    family_id: str
    user_id: str
    privilege: PrivilegeRead
    unlocked_at: datetime
    used_count: int
    last_used_at: datetime | None = None
