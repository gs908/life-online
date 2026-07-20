"""用户 DTO。"""
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
    level: int
    xp: int
    time_coins: int
    daily_abandon_count: int
    last_login_date: date | None = None
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
    time_coins: int | None = None
    level: int | None = None
    xp: int | None = None
    privileges_unlocked: list[str] | None = None
