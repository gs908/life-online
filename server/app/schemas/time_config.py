"""时间币配置 DTO。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class TimeConfigExceptionRead(BaseModel):
    day_of_week: int = Field(..., ge=0, le=6, description="0=Sun, 6=Sat")
    coin_amount: int = Field(..., ge=0)


class TimeConfigRead(BaseModel):
    family_id: str
    default_daily_allowance: int
    exceptions: list[TimeConfigExceptionRead] = Field(default_factory=list)


class TimeConfigUpdate(BaseModel):
    default_daily_allowance: int | None = Field(default=None, ge=0)
    exceptions: list[TimeConfigExceptionRead] | None = None
