"""特权使用记录 DTO。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class RedemptionCreate(BaseModel):
    user_id: str
    privilege_id: str | None = None
    privilege_title: str | None = None
    cost: str | None = None


class RedemptionRead(BaseModel):
    id: str
    family_id: str
    user_id: str
    privilege_id: str | None = None
    privilege_title: str
    cost: str | None
    date: datetime
