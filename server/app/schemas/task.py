"""任务 DTO。"""
from __future__ import annotations

from datetime import datetime, time

from pydantic import BaseModel, Field

from app.models.enums import TaskCategory, TaskStatus, TaskType


class TaskTemplateCreate(BaseModel):
    season_id: str
    library_id: str | None = None
    category: TaskCategory | None = None
    title: str
    description: str = ""
    lore_snippet: str | None = None
    xp_reward: int = Field(default=50, ge=0)
    type: TaskType = TaskType.DAILY
    target_child_id: str | None = None
    required_start_time: time | None = None
    reminder_message: str | None = None
    reminder_minutes_before: int = 15
    time_deposit: int = 10
    is_active: bool = True


class TaskTemplateRead(BaseModel):
    id: str
    family_id: str
    season_id: str
    creator_account_id: str | None = None
    library_id: str | None = None
    target_child_id: str | None = None
    category: TaskCategory | None = None
    title: str
    description: str
    lore_snippet: str | None = None
    xp_reward: int
    type: TaskType
    required_start_time: time | None = None
    reminder_message: str | None = None
    reminder_minutes_before: int
    time_deposit: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class TaskCreate(TaskTemplateCreate):
    """兼容旧创建接口:创建模板并生成一条初始实例。"""
    target_user_id: str | None = None
    deadline: datetime | None = None
    expire_at: datetime | None = None


class TaskRead(BaseModel):
    id: str
    family_id: str
    season_id: str
    template_id: str | None = None
    creator_account_id: str | None = None
    target_child_id: str | None = None
    assignee_child_id: str | None = None
    category: TaskCategory | None = None
    title: str
    description: str
    lore_snippet: str | None
    xp_reward: int
    type: TaskType
    status: TaskStatus
    deadline: datetime | None
    expire_at: datetime | None = None
    required_start_time: time | None
    proof_url: str | None = None
    rating: int | None
    review_comment: str | None = None
    xp_awarded: int | None = None
    coin_delta: int = 0
    abandon_count_at_submit: int = 0
    started_at: datetime | None
    submitted_at: datetime | None
    completed_at: datetime | None
    reminder_message: str | None
    reminder_minutes_before: int
    time_deposit: int
    created_at: datetime
    updated_at: datetime

    # 兼容旧前端字段名,后续前端迁移完成后可删除。
    creator_id: str | None = None
    target_user_id: str | None = None
    assignee_id: str | None = None


class TaskStartRequest(BaseModel):
    child_id: str | None = None
    user_id: str | None = None


class TaskSubmitRequest(BaseModel):
    proof_object_key: str


class TaskApproveRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    comment: str | None = None


class TaskRejectRequest(BaseModel):
    comment: str | None = None


class TaskAbandonRequest(BaseModel):
    child_id: str | None = None
    user_id: str | None = None
