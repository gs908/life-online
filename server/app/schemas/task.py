"""任务 DTO。"""
from __future__ import annotations

from datetime import date, datetime, time
from typing import Annotated

from apscheduler.triggers.cron import CronTrigger
from pydantic import BaseModel, Field, model_validator
from app.models.enums import PoolPolicy, TaskCategory, TaskStatus, TaskType, TimedMode, TriggerKind

Weekday = Annotated[int, Field(ge=0, le=6)]


def validate_timed_mode(
    mode: str | TimedMode | None,
    deadline_time: time | None,
    start_time: time | None,
    duration_minutes: int | None,
) -> None:
    """timed_mode 与时间窗字段一致性校验(docs/12 块 A),不一致抛 ValueError -> 422。

    - DEADLINE 需 deadline_time;
    - DURATION 需 start_time + duration_minutes;
    - NONE 三者皆空。
    """
    mode_value = mode.value if hasattr(mode, "value") else str(mode or TimedMode.NONE)
    if mode_value == TimedMode.NONE.value:
        if deadline_time is not None or start_time is not None or duration_minutes is not None:
            raise ValueError("timed_mode=NONE 时 deadline_time/start_time/duration_minutes 必须全部为空")
    elif mode_value == TimedMode.DEADLINE.value:
        if deadline_time is None:
            raise ValueError("timed_mode=DEADLINE 必须提供 deadline_time")
        if start_time is not None or duration_minutes is not None:
            raise ValueError("timed_mode=DEADLINE 不接受 start_time/duration_minutes")
    elif mode_value == TimedMode.DURATION.value:
        if start_time is None or duration_minutes is None:
            raise ValueError("timed_mode=DURATION 必须提供 start_time 和 duration_minutes")
        if deadline_time is not None:
            raise ValueError("timed_mode=DURATION 不接受 deadline_time")
    else:
        raise ValueError(f"未知的 timed_mode: {mode_value}")


def validate_trigger_fields(trigger: "TaskTriggerCreate") -> None:
    """触发规则按 kind 校验必填字段与格式,不合法抛 ValueError -> 422。"""
    kind_value = trigger.kind.value if hasattr(trigger.kind, "value") else str(trigger.kind)
    if trigger.ends_on is not None and trigger.starts_on is not None and trigger.ends_on < trigger.starts_on:
        raise ValueError("ends_on 不能早于 starts_on")
    if kind_value == TriggerKind.DAILY.value:
        return
    if kind_value == TriggerKind.WEEKDAYS.value:
        if not trigger.weekdays:
            raise ValueError("kind=WEEKDAYS 必须提供非空 weekdays(0=周一..6=周日)")
        return
    if kind_value == TriggerKind.MONTHLY.value:
        if trigger.day_of_month is None:
            raise ValueError("kind=MONTHLY 必须提供 day_of_month(1-31,月末不足取当月最后一天)")
        return
    if kind_value == TriggerKind.CRON.value:
        if not trigger.cron_expr:
            raise ValueError("kind=CRON 必须提供 cron_expr(5 段,家庭本地时区 Asia/Shanghai)")
        try:
            CronTrigger.from_crontab(trigger.cron_expr)
        except ValueError as exc:
            raise ValueError(f"cron_expr 不是合法的 5 段 cron 表达式: {exc}") from exc
        return
    if kind_value == TriggerKind.ONCE.value:
        if trigger.starts_on is None:
            raise ValueError("kind=ONCE 必须提供 starts_on(在该日生成一次)")
        return
    raise ValueError(f"未知的触发类型: {kind_value}")


class TaskTriggerCreate(BaseModel):
    kind: TriggerKind
    cron_expr: str | None = None
    weekdays: list[Weekday] | None = None
    day_of_month: int | None = Field(default=None, ge=1, le=31)
    generate_at: time = time(0, 0)
    starts_on: date | None = None
    ends_on: date | None = None
    is_active: bool = True

    @model_validator(mode="after")
    def _check_fields(self) -> "TaskTriggerCreate":
        validate_trigger_fields(self)
        return self


class TaskTriggerRead(BaseModel):
    id: str
    template_id: str
    kind: TriggerKind
    cron_expr: str | None = None
    weekdays: list[Weekday] | None = None
    day_of_month: int | None = None
    generate_at: time
    starts_on: date | None = None
    ends_on: date | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


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
    # 显式押金:缺省时由 coin_service.resolve_deposit 按耗时/类型解析落库
    time_deposit: int | None = Field(default=None, ge=0)
    is_active: bool = True
    # ---- docs/12 块 A ----
    timed_mode: TimedMode = TimedMode.NONE
    deadline_time: time | None = None
    start_time: time | None = None
    duration_minutes: int | None = Field(default=None, ge=1)
    pool_policy: PoolPolicy = PoolPolicy.REUSE_UNTIL_CONSUMED
    # 押金耗时输入(DEV-34 块 C):1 分钟 ~ 24 小时
    estimated_minutes: int | None = Field(default=None, ge=1, le=24 * 60)
    # 难度 1-5(DEV-34 块 C 语义,块 A 契约可空 = 未评星):只影响 XP,不影响押金
    difficulty: int | None = Field(default=None, ge=1, le=5)
    triggers: list[TaskTriggerCreate] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_timed_mode(self) -> "TaskTemplateCreate":
        validate_timed_mode(self.timed_mode, self.deadline_time, self.start_time, self.duration_minutes)
        return self


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
    timed_mode: TimedMode = TimedMode.NONE
    deadline_time: time | None = None
    start_time: time | None = None
    duration_minutes: int | None = None
    pool_policy: PoolPolicy = PoolPolicy.REUSE_UNTIL_CONSUMED
    estimated_minutes: int | None = None
    difficulty: int | None = None
    deprecated_at: datetime | None = None
    deprecated_reason: str | None = None
    triggers: list[TaskTriggerRead] = []
    created_at: datetime
    updated_at: datetime


class TaskTemplateUpdate(BaseModel):
    """PATCH /scn/task-templates/{id} 请求体:全部可选,未提供的字段保持不变。

    timed_mode/时间窗的一致性在服务层对"合并后的完整模板"复验(422),
    避免部分更新绕过 TaskTemplateCreate 的创建期校验。
    """

    category: TaskCategory | None = None
    title: str | None = None
    description: str | None = None
    lore_snippet: str | None = None
    xp_reward: int | None = Field(default=None, ge=0)
    type: TaskType | None = None
    target_child_id: str | None = None
    required_start_time: time | None = None
    reminder_message: str | None = None
    reminder_minutes_before: int | None = None
    time_deposit: int | None = None
    is_active: bool | None = None
    timed_mode: TimedMode | None = None
    deadline_time: time | None = None
    start_time: time | None = None
    duration_minutes: int | None = Field(default=None, ge=1)
    pool_policy: PoolPolicy | None = None
    estimated_minutes: int | None = Field(default=None, ge=1)
    difficulty: int | None = Field(default=None, ge=1, le=5)
    triggers: list[TaskTriggerCreate] | None = None


class TaskTemplateDeprecate(BaseModel):
    reason: str | None = Field(default=None, max_length=128)


class TaskTemplateRegenerate(BaseModel):
    """终结未消费实例并立即生成;当前无参数,占位以便后续扩展(如指定日期)。"""


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
    generated_for_date: date | None = None
    required_start_time: time | None
    # 可空 = 模板未评星(块 A 契约);旧前端未消费该字段
    difficulty: int | None = None
    estimated_minutes: int | None = None
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


# ---- 模板库(docs/06 §2 / docs/12 块 A) ----


class TemplateLibraryRead(BaseModel):
    id: str
    family_id: str | None = None
    category: TaskCategory
    tags: list[str] = []
    title: str
    description: str = ""
    suggested_xp: int
    suggested_time_deposit: int
    suggested_type: TaskType
    is_active: bool
    is_favorite: bool = False
    favorite_of: str | None = Field(default=None, description="收藏行指向的原始库条目 id")


class TemplateLibraryApplyRequest(BaseModel):
    season_id: str
    target_child_id: str | None = None
