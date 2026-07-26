"""赛季 DTO。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.models.enums import ThemeId


class SeasonCreate(BaseModel):
    name: str
    theme_id: ThemeId = ThemeId.DEFAULT
    narrative_context: str = ""
    start_date: datetime
    end_date: datetime | None = None


class SeasonUpdate(BaseModel):
    name: str | None = None
    theme_id: ThemeId | None = None
    narrative_context: str | None = None
    end_date: datetime | None = None
    is_active: bool | None = None


class SeasonRead(BaseModel):
    id: str
    family_id: str
    name: str
    theme_id: ThemeId
    narrative_context: str
    start_date: datetime
    end_date: datetime | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class SeasonHistoryItem(BaseModel):
    season: SeasonRead
    total_tasks: int
    completed_tasks: int
    total_xp: int
