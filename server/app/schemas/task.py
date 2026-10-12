"""任务 DTO。"""
from __future__ import annotations

from datetime import datetime, time

from pydantic import BaseModel, Field

from app.models.enums import ProofKind, TaskCategory, TaskStatus, TaskType


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
    difficulty: int = Field(default=2, ge=1, le=5)
    estimated_minutes: int | None = Field(default=None, ge=1, le=24 * 60)
    # 显式押金:缺省时由 coin_service.resolve_deposit 按耗时/类型解析落库
    time_deposit: int | None = Field(default=None, ge=0)
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
    difficulty: int = 2
    estimated_minutes: int | None = None
    time_deposit: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class TaskCreate(TaskTemplateCreate):
    """兼容旧创建接口:创建模板并生成一条初始实例。"""
    target_user_id: str | None = None
    deadline: datetime | None = None
    expire_at: datetime | None = None


class TaskProofRead(BaseModel):
    """任务证据(DEV-33 块 E):scn_task_proof 行的读取形状。

    `url` 按 object_key 现算(minio 预签名/local 稳定路径),与 UploadRead.access_url 同口径。
    """

    id: str
    task_instance_id: str
    kind: ProofKind
    url: str | None = None
    size: int
    content_type: str
    created_at: datetime | None = None


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
    difficulty: int = 2
    estimated_minutes: int | None = None
    proof_url: str | None = None       # 过渡:= proofs[0].url(读取以 proofs 为准)
    proofs: list[TaskProofRead] = Field(default_factory=list)
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
    """多证据提交(DEV-33 块 E)。

    - `proof_object_keys`:一次提交的全部证明文件 object_key(先经 POST /sys/uploads
      purpose=task_proof 上传);逐个校验存在/归属/purpose/占用后创建 scn_task_proof 行。
    - `proof_object_key`:过渡兼容字段,旧客户端单值提交仍可用(等价于单元素列表)。
    """
    proof_object_keys: list[str] = Field(default_factory=list)
    proof_object_key: str | None = None  # 过渡:旧客户端单值字段


class TaskApproveRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    comment: str | None = None


class TaskRejectRequest(BaseModel):
    comment: str | None = None


class TaskAbandonRequest(BaseModel):
    child_id: str | None = None
    user_id: str | None = None


class TaskDepositPreviewRequest(BaseModel):
    """管理端表单实时预览押金:难度 + 预计耗时 -> 押金。难度不影响押金,仅为表单完整性透传。"""
    type: TaskType = TaskType.DAILY
    estimated_minutes: int | None = Field(default=None, ge=1, le=24 * 60)
    time_deposit: int | None = Field(default=None, ge=0)
    difficulty: int | None = Field(default=None, ge=1, le=5)


class TaskDepositPreviewResponse(BaseModel):
    time_deposit: int
    daily_allowance: int
    capped_by_allowance: bool
