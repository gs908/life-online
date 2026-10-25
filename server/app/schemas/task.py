"""任务 DTO。"""
from __future__ import annotations

from datetime import date, datetime, time
from typing import Annotated

from apscheduler.triggers.cron import CronTrigger
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.models.enums import (
    ContentMode,
    ContentSource,
    PoolPolicy,
    ProofKind,
    TaskCategory,
    TaskParticipantRole,
    TaskParticipantStatus,
    TaskStatus,
    TaskType,
    TimedMode,
    TriggerKind,
)

Weekday = Annotated[int, Field(ge=0, le=6)]

# 逐实例微调的三个字段(DEV-50):全是**快照**列 —— 生成时写入模板当前值,
# 之后可独立调整。三个字段语义完全同构,故共用同一条"显式 null 一律拒绝"规则。
SNAPSHOT_FIELDS = ("difficulty", "time_deposit", "xp_reward")


def reject_explicit_null(model, fields=SNAPSHOT_FIELDS) -> None:
    """三个快照字段不接受显式 `null`(→ 422)。

    用 `model_fields_set` 区分"未提供"与"显式 null":未提供 = 保持不变(或生成
    时用模板值);显式 `null` = 客户端 bug。**不静默忽略、也不静默转译成
    "去查模板值"** —— 后者会把"一次性填入"伪装成"持续跟随",让家长误以为
    以后改模板会同步。宁可让 bug 暴露成字段级 422。

    "恢复模板值"的正确做法由前端完成:取模板当前值,作为具体数字提交。
    """
    provided = getattr(model, "model_fields_set", set())
    for name in fields:
        if name in provided and getattr(model, name) is None:
            raise ValueError(f"{name} 不可为空;如需恢复模板值,请显式提交模板当前值")


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
    # 可空(DEV-50):模板可跨赛季,赛季只是可选"来源标签";实际归属赛季在
    # 生成时取当时的激活赛季。
    season_id: str | None = None
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
    # ---- CHAIN 链式字段(DEV-36 块 F;仅 CHAIN 类型可用,创建时校验) ----
    chain_key: str | None = Field(default=None, max_length=64)
    chain_order: int = Field(default=1, ge=1)
    chain_total: int = Field(default=1, ge=1)
    # 押金耗时输入(DEV-34 块 C):1 分钟 ~ 24 小时
    estimated_minutes: int | None = Field(default=None, ge=1, le=24 * 60)
    # 难度 1-5(DEV-34 块 C 语义,块 A 契约可空 = 未评星):只影响 XP,不影响押金
    difficulty: int | None = Field(default=None, ge=1, le=5)
    # ---- 任务内容生成(docs/15 R24;DEV-50 默认值翻转)----
    # 默认 LLM:口径是"生成任务时要调用 LLM 结合赛季背景完成动态内容生成"。
    # 需要确定性文本的任务可显式传 STATIC 退出。
    content_mode: ContentMode = ContentMode.LLM
    # 任务要点:LLM 叙事生成的输入;为空时生成器回落用 description
    content_brief: str | None = None
    triggers: list[TaskTriggerCreate] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_timed_mode(self) -> "TaskTemplateCreate":
        validate_timed_mode(self.timed_mode, self.deadline_time, self.start_time, self.duration_minutes)
        return self


class TaskTemplateRead(BaseModel):
    id: str
    family_id: str
    # 可空(DEV-50):模板可跨赛季,season_id 只是可选"来源标签"。
    season_id: str | None = None
    # 来源赛季名(前端「来源赛季:{name}」弱提示用);season_id 为空时为 None。
    # 由后端一并返回,避免前端再拉一次赛季列表自己做 map。
    season_name: str | None = None
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
    chain_key: str | None = None
    chain_order: int
    chain_total: int
    estimated_minutes: int | None = None
    difficulty: int | None = None
    content_mode: ContentMode = ContentMode.LLM
    content_brief: str | None = None
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
    content_mode: ContentMode | None = None
    content_brief: str | None = None
    triggers: list[TaskTriggerCreate] | None = None


class TaskTemplateDeprecate(BaseModel):
    reason: str | None = Field(default=None, max_length=128)


class TaskTemplateRegenerate(BaseModel):
    """终结未消费实例并立即生成;当前无参数,占位以便后续扩展(如指定日期)。"""


class TaskGenerateRequest(BaseModel):
    """「选模板 → 生成」入参(DEV-50)。

    - `target_date` 缺省 = 家庭本地时区今天;服务端校验"仅允许 ≥ 今天"与
      上限(见 task_template_service.MANUAL_GENERATE_MAX_AHEAD_DAYS)。
      入参叫 `target_date`(意图:为哪一天生成),出参回显 `generated_for_date`
      (事实:实例的逻辑日),刻意不同名。
    - 三个可覆盖字段**未提供 = 用模板值**(快照);**显式 `null` → 422**。
      生成路径不存在"清除覆盖"的动作 —— 新建实例没有可清除的覆盖。
    - `target_child_id` 缺省 = 用模板值;显式 `null` 在此语义为"不指定"。

    `extra="forbid"`(DEV-50 审查):多传字段直接 422。静默忽略会掩盖客户端 bug
    —— 例如往 PATCH 里塞 `season_id`(实例赛季不可改)会被无声吞掉,客户端以为
    改成功了。
    """

    model_config = ConfigDict(extra="forbid")

    target_date: date | None = None
    difficulty: int | None = Field(default=None, ge=1, le=5)
    time_deposit: int | None = Field(default=None, ge=0)
    xp_reward: int | None = Field(default=None, ge=0)
    target_child_id: str | None = None

    @model_validator(mode="after")
    def _check_snapshots(self) -> "TaskGenerateRequest":
        reject_explicit_null(self)
        return self


class TaskTuneRequest(BaseModel):
    """逐实例微调入参(DEV-50,`PATCH /scn/task-instances/{id}`)。

    三个字段都是**快照**,语义同构:`exclude_unset` —— 未提供 = 保持不变;
    显式 `null` → 422(见 `reject_explicit_null`)。「恢复模板值」由前端取模板
    当前值后作为具体数字提交。

    实例的 `season_id` **不可改**(任务不跨赛季),故不在本契约中。
    `extra="forbid"`:多传字段(如 `season_id`)一律 422,不静默忽略 —— 否则
    客户端会以为"改成功了"。
    """

    model_config = ConfigDict(extra="forbid")

    difficulty: int | None = Field(default=None, ge=1, le=5)
    time_deposit: int | None = Field(default=None, ge=0)
    xp_reward: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _check_snapshots(self) -> "TaskTuneRequest":
        reject_explicit_null(self)
        return self


class TaskCreate(TaskTemplateCreate):
    """兼容旧创建接口:创建模板并生成一条初始实例。"""
    target_user_id: str | None = None
    deadline: datetime | None = None
    expire_at: datetime | None = None


class TaskProofRead(BaseModel):
    """任务证据(DEV-33 块 E):scn_task_proof 行的读取形状。

    `url` 按 object_key 现算(minio 预签名/local 稳定路径),与 UploadRead.access_url 同口径。
    `uploaded_by`(DEV-40,docs/13 §4 裁决 Q3):上传者账号;前端据此为
    家长参与者提交的证据渲染"家长代交"标注。
    """

    id: str
    task_instance_id: str
    kind: ProofKind
    url: str | None = None
    size: int
    content_type: str
    uploaded_by: str | None = None
    created_at: datetime | None = None


class TaskParticipantRead(BaseModel):
    """COOP 参与者(非 COOP 任务该列表为空)。"""

    account_id: str
    child_id: str | None = None
    role: TaskParticipantRole
    # 参与者子状态(docs/13 定稿版 §3):JOINED/SUBMITTED/DONE/QUIT
    participant_status: TaskParticipantStatus = TaskParticipantStatus.JOINED
    confirmed_at: datetime | None = None
    deposit_share: int
    xp_awarded: int | None = None


class TaskRead(BaseModel):
    id: str
    family_id: str
    season_id: str
    # 实例所属赛季名(DEV-50):模板可跨赛季后,实例列表只靠 season_id 分不清
    # 属于哪个赛季;由后端一并返回,避免前端自己 map。
    season_name: str | None = None
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
    # CHAIN:链中位置(1-based)与总步数,链末步骤享受链末 XP 加成
    chain_index: int | None = None
    chain_total: int | None = None
    # 叙事来源(docs/15 R25);generation_meta 为内部数据,不出接口
    content_source: ContentSource = ContentSource.TEMPLATE
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
    """多证据提交(DEV-33 块 E)。

    - `proof_object_keys`:一次提交的全部证明文件 object_key(先经 POST /sys/uploads
      purpose=task_proof 上传);逐个校验存在/归属/purpose/占用后创建 scn_task_proof 行。
    - `proof_object_key`:过渡兼容字段,旧客户端单值提交仍可用(等价于单元素列表)。
    """
    proof_object_keys: list[str] = Field(default_factory=list)
    proof_object_key: str | None = None  # 过渡:旧客户端单值字段


class TaskApproveRequest(BaseModel):
    """父母审核(docs/13 定稿版 §3.1/§4,DEV-40)。

    - 都不带可选字段 → 整单通过(仅 PENDING_REVIEW;单人任务唯一路径);
    - `child_id` / `participant_id` → 逐人确认该参与者(家长参与者无 child_id,
      用 participant_id 定位);入口 IN_PROGRESS/PENDING_REVIEW,守卫=该参与者已 SUBMITTED;
    - `settle_partial=true` → 部分通过判退收尾(仅 COOP、仅 IN_PROGRESS):
      已交者退份额结算,未交者按放弃阶梯打折退且不递增放弃计数。
    """

    rating: int = Field(..., ge=1, le=5)
    comment: str | None = None
    child_id: str | None = None
    participant_id: str | None = None
    settle_partial: bool = False


class TaskRejectRequest(BaseModel):
    comment: str | None = None


class TaskAbandonRequest(BaseModel):
    child_id: str | None = None
    user_id: str | None = None


class TaskDepositPreviewRequest(BaseModel):
    """管理端表单实时预览押金:难度 + 预计耗时 -> 押金。难度不影响押金,仅为表单完整性透传。

    `for_date`(DEV-50):封顶依赖的"当日配额"按**星期几**不同
    (`coin_service.compute_daily_allowance` 读 `ScnTimeConfig.exceptions.day_of_week`),
    所以为未来日期生成时,拿今天的配额算出的上限会失真。缺省 = 今天。
    """
    type: TaskType = TaskType.DAILY
    estimated_minutes: int | None = Field(default=None, ge=1, le=24 * 60)
    time_deposit: int | None = Field(default=None, ge=0)
    difficulty: int | None = Field(default=None, ge=1, le=5)
    for_date: date | None = None


class TaskDepositPreviewResponse(BaseModel):
    time_deposit: int
    daily_allowance: int
    capped_by_allowance: bool


class TaskBriefGenerateRequest(BaseModel):
    """「任务要点 → 任务建议」入参(DEV-60,docs/08 §6C)。

    任务板「创建新任务」未选模板时,家长填任务要点、点「生成」,后端把要点交给
    LLM 润色成任务建议**反显回表单**;确认后再走既有的创建路径落库。

    - `brief` 即 `ai_service.generate_quest` 的 `topic`(任务实质,Season 无关);
    - `season_id` 缺省 = 当前激活赛季的剧情,作为叙事背景(与生成器同口径);
    - `target_date` 只用于**建议押金**的当日配额封顶(配额按星期几不同),缺省
      = 家庭本地时区今天;校验口径与 `POST /scn/task-templates/{id}/generate`
      一致(仅允许 ≥ 今天、最多提前 30 天);
    - `child_level` 只影响 LLM 的语气与难度建议。

    `extra="forbid"`:多传字段直接 422,不静默忽略(DEV-50 审查口径)。
    """
    model_config = ConfigDict(extra="forbid")

    brief: str = Field(..., min_length=1, max_length=500)
    season_id: str | None = None
    target_date: date | None = None
    child_level: int = Field(default=1, ge=1, le=200)


class TaskBriefSuggestion(BaseModel):
    """任务建议出参(DEV-60):只回渲染建议,**不入库**。

    前端拿这 5 个字段回填「创建新任务」表单,由用户确认/改写后再提交创建。
    """
    title: str
    description: str
    xp_reward: int
    difficulty: int
    time_deposit: int


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
    # DEV-50:与 POST /scn/task-templates 同源口径 —— 模板不绑赛季,套用时可省。
    season_id: str | None = None
    target_child_id: str | None = None
