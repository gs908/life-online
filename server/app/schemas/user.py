"""用户/账号 DTO。"""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from app.models.enums import UserRole


class UserRead(BaseModel):
    id: str
    family_id: str
    role: UserRole
    name: str
    avatar: str
    locale: str = "zh-CN"
    child_id: str | None = None
    level: int = 1
    xp: int = 0
    time_coins: int = 0
    daily_abandon_count: int = 0
    last_login_date: date | None = None
    current_season_id: str | None = None
    privileges_unlocked: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class UserCreate(BaseModel):
    family_id: str
    role: UserRole
    name: str
    avatar: str = "⚔️"


class AdventurerCreate(BaseModel):
    name: str
    avatar: str = "⚔️"


class UserUpdate(BaseModel):
    name: str | None = None
    avatar: str | None = None
    locale: str | None = None
    time_coins: int | None = None
    level: int | None = None
    xp: int | None = None
    current_season_id: str | None = None
    privileges_unlocked: list[str] | None = None
