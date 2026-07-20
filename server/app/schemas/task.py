"""任务 DTO。"""
from __future__ import annotations

from datetime import datetime, time

from pydantic import BaseModel, Field

from app.models.enums import TaskStatus, TaskType


class TaskCreate(BaseModel):
    season_id: str
    title: str
    description: str = ""
    lore_snippet: str | None = None
    xp_reward: int = Field(default=50, ge=0)
    type: TaskType = TaskType.DAILY
    target_user_id: str | None = None
    deadline: datetime | None = None
    required_start_time: time | None = None
    reminder_message: str | None = None
    reminder_minutes_before: int = 15
    time_deposit: int = 10


class TaskRead(BaseModel):
    id: str
    family_id: str
    season_id: str
    creator_id: str | None
    target_user_id: str | None
    assignee_id: str | None
    title: str
    description: str
    lore_snippet: str | None
    xp_reward: int
    type: TaskType
    status: TaskStatus
    deadline: datetime | None
    required_start_time: time | None
    proof_url: str | None = None
    rating: int | None
    started_at: datetime | None
    submitted_at: datetime | None
    completed_at: datetime | None
    reminder_message: str | None
    reminder_minutes_before: int
    time_deposit: int
    created_at: datetime
    updated_at: datetime


class TaskStartRequest(BaseModel):
    user_id: str


class TaskSubmitRequest(BaseModel):
    proof_object_key: str


class TaskApproveRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    comment: str | None = None


class TaskAbandonRequest(BaseModel):
    user_id: str
