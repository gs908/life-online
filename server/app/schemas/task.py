"""任务 DTO。"""
from __future__ import annotations

from datetime import datetime, time

from pydantic import BaseModel, Field

from app.models.enums import TaskCategory, TaskParticipantRole, TaskStatus, TaskType


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
    # CHAIN 链式字段(仅 CHAIN 类型可用,创建时校验)
    chain_key: str | None = Field(default=None, max_length=64)
    chain_order: int = Field(default=1, ge=1)
    chain_total: int = Field(default=1, ge=1)
    # 递进难度:预计完成分钟数(链内步骤顺延窗口的默认来源)/ 难度 1-5
    estimated_minutes: int | None = Field(default=None, ge=1)
    difficulty: int = Field(default=1, ge=1, le=5)


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
    chain_key: str | None = None
    chain_order: int
    chain_total: int
    estimated_minutes: int | None = None
    difficulty: int
    created_at: datetime
    updated_at: datetime


class TaskCreate(TaskTemplateCreate):
    """兼容旧创建接口:创建模板并生成一条初始实例。"""
    target_user_id: str | None = None
    deadline: datetime | None = None
    expire_at: datetime | None = None


class TaskParticipantRead(BaseModel):
    """COOP 参与者(非 COOP 任务该列表为空)。"""

    account_id: str
    child_id: str | None = None
    role: TaskParticipantRole
    confirmed_at: datetime | None = None
    deposit_share: int
    xp_awarded: int | None = None


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
    # CHAIN:链中位置(1-based)与总步数,链末步骤享受链末 XP 加成
    chain_index: int | None = None
    chain_total: int | None = None
    estimated_minutes: int | None = None
    difficulty: int | None = None
    # COOP 参与者
    participants: list[TaskParticipantRead] = Field(default_factory=list)
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
