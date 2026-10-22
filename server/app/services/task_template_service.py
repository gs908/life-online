"""任务模板服务:模板 CRUD / 生命周期 / 再生成,及模板库列表-收藏-套用(docs/12 块 A)。

与 task_service(实例状态机)分界:本模块只管模板与生成编排,
实例状态流转(押金/审核/过期)复用 task_service 的语义。
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.common.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from app.common.timeutil import today_bj, utcnow
from app.models.enums import (
    CoinTransactionType,
    PoolPolicy,
    TaskStatus,
    TaskType,
    TimedMode,
    TriggerKind,
)
from app.models.scn_season import ScnSeason
from app.models.scn_task_instance import ScnTaskInstance
from app.models.scn_task_template import ScnTaskTemplate
from app.models.scn_task_template_library import ScnTaskTemplateLibrary
from app.models.scn_task_template_trigger import ScnTaskTemplateTrigger
from app.models.sys_child import SysChild
from app.models.sys_family import SysFamily
from app.schemas.task import (
    TaskGenerateRequest,
    TaskTemplateCreate,
    TaskTemplateUpdate,
    TaskTriggerCreate,
    validate_timed_mode,
)
from app.services import chain_service, coin_service, task_generator_service

log = logging.getLogger(__name__)

# 收藏行在 scn_task_template_library 上的标记:家庭级收藏指向原始条目。
_FAVORITE_OF_KEY = "favorite_of"

# 「选模板 → 生成」允许的最远提前天数(DEV-50 契约):防误建远期实例。
MANUAL_GENERATE_MAX_AHEAD_DAYS = 30


def _enum_value(value) -> str:
    return value.value if hasattr(value, "value") else str(value)


async def _ensure_season(db: AsyncSession, *, family_id: str, season_id: str) -> ScnSeason:
    season = await db.get(ScnSeason, season_id)
    if not season:
        raise NotFoundError(f"赛季 {season_id} 不存在")
    if season.family_id != family_id:
        raise PermissionDeniedError("只能在自己家庭的赛季中创建任务模板")
    return season


async def get_template(db: AsyncSession, template_id: str) -> ScnTaskTemplate:
    template = (
        await db.execute(
            select(ScnTaskTemplate)
            .where(ScnTaskTemplate.id == template_id)
            .options(selectinload(ScnTaskTemplate.triggers))
        )
    ).scalar_one_or_none()
    if not template:
        raise NotFoundError(f"任务模板 {template_id} 不存在")
    return template


async def get_family_template(
    db: AsyncSession, *, template_id: str, family_id: str,
) -> ScnTaskTemplate:
    template = await get_template(db, template_id)
    if template.family_id != family_id:
        raise PermissionDeniedError("只能操作自己家庭的任务模板")
    return template


async def is_family_owner(db: AsyncSession, *, family_id: str, account_id: str) -> bool:
    """管理端权限的当前口径:家庭 owner(创建家庭的家长)。"""
    family = await db.get(SysFamily, family_id)
    return family is not None and family.owner_id == account_id


def default_triggers_for_type(template_type) -> list[ScnTaskTemplateTrigger]:
    """类型默认触发规则(docs/12 块 A):未显式给 triggers 时按类型补一条。

    - DAILY / TIMED -> 每天 00:00(TIMED 的"何时截止"由时间窗管,触发只管何时生成);
    - CHALLENGE     -> 每周一 00:00(cron 表达);
    - 一次性(ONCE)/ CHAIN / COOP -> 无默认,必须显式给规则。
    """
    type_value = _enum_value(template_type)
    if type_value in (TaskType.DAILY.value, TaskType.TIMED.value):
        return [ScnTaskTemplateTrigger(kind=TriggerKind.DAILY, generate_at=time(0, 0))]
    if type_value == TaskType.CHALLENGE.value:
        return [ScnTaskTemplateTrigger(kind=TriggerKind.CRON, cron_expr="0 0 * * 1")]
    return []


def _build_triggers(payload_triggers) -> list[ScnTaskTemplateTrigger]:
    return [
        ScnTaskTemplateTrigger(
            kind=t.kind,
            cron_expr=t.cron_expr,
            weekdays=t.weekdays,
            day_of_month=t.day_of_month,
            generate_at=t.generate_at,
            starts_on=t.starts_on,
            ends_on=t.ends_on,
            is_active=t.is_active,
        )
        for t in payload_triggers
    ]


async def create_template(
    db: AsyncSession, *, family_id: str, creator_id: str, payload: TaskTemplateCreate,
) -> ScnTaskTemplate:
    """创建模板 + 触发规则(不强制建实例),随后立即对该模板跑一次生成。

    押金与旧 create_task 路径同口径(DEV-34 块 C+D):创建时即由
    `coin_service.resolve_deposit` 解析落库(显式值 > 模板库 suggested_time_deposit
    > 按预计耗时 × 类型默认值),此后各环节直接读 `time_deposit` 字段。

    DEV-50:模板可跨赛季 —— `season_id` 变为**可选**的"来源标签",提供时校验
    归属与存在,不提供即无来源赛季(实例的实际赛季在生成时取激活赛季)。
    """
    if payload.season_id is not None:
        await _ensure_season(db, family_id=family_id, season_id=payload.season_id)

    # CHAIN 链式模板(DEV-36 块 F):链字段完整性校验;后续步骤(chain_order>1)
    # 不给默认触发规则,创建后不会长出实例(实例由链首投放 + 逐步解锁生成)。
    await chain_service.validate_chain_template(
        db,
        family_id=family_id,
        task_type=payload.type,
        chain_key=payload.chain_key,
        chain_order=payload.chain_order,
        chain_total=payload.chain_total,
    )

    explicit_deposit = payload.time_deposit
    if explicit_deposit is None and payload.library_id:
        # 模板库套用:用 suggested_time_deposit 播种(显式值,仍受类型范围/配额封顶约束)
        library = await db.get(ScnTaskTemplateLibrary, payload.library_id)
        if library is not None and library.family_id not in (None, family_id):
            raise PermissionDeniedError("只能套用平台或自己家庭的模板库")
        if library is not None:
            explicit_deposit = library.suggested_time_deposit

    deposit = await coin_service.resolve_deposit(
        db,
        family_id=family_id,
        task_type=payload.type,
        estimated_minutes=payload.estimated_minutes,
        explicit_deposit=explicit_deposit,
        day=today_bj(),
    )

    template = ScnTaskTemplate(
        family_id=family_id,
        season_id=payload.season_id,
        creator_account_id=creator_id,
        library_id=payload.library_id,
        target_child_id=payload.target_child_id,
        category=payload.category,
        title=payload.title,
        description=payload.description,
        lore_snippet=payload.lore_snippet,
        xp_reward=payload.xp_reward,
        type=payload.type,
        required_start_time=payload.required_start_time,
        reminder_message=payload.reminder_message,
        reminder_minutes_before=payload.reminder_minutes_before,
        time_deposit=deposit,
        is_active=payload.is_active,
        timed_mode=payload.timed_mode,
        deadline_time=payload.deadline_time,
        start_time=payload.start_time,
        duration_minutes=payload.duration_minutes,
        pool_policy=payload.pool_policy,
        chain_key=payload.chain_key,
        chain_order=payload.chain_order,
        chain_total=payload.chain_total,
        estimated_minutes=payload.estimated_minutes,
        difficulty=payload.difficulty,
        content_mode=payload.content_mode,
        content_brief=payload.content_brief,
    )
    triggers = _build_triggers(payload.triggers) or default_triggers_for_type(payload.type)
    template.triggers = triggers
    db.add(template)
    await db.commit()

    # 模板创建后立即补一次生成(force:generate_at 未到也先生成当日实例,
    # 规则未命中 today 时自然返回 not_due)。
    instance, action = await task_generator_service.generate_for_template(
        db, template, force=True,
    )
    log.info("template %s created, initial generation action=%s instance=%s",
             template.id, action, getattr(instance, "id", None))
    return template


_TEMPLATE_UPDATABLE_FIELDS = (
    "category", "title", "description", "lore_snippet", "xp_reward", "type",
    "target_child_id",  # Mars #1:此前列在 PATCH 中被校验却从不生效(静默丢弃);置 None = 清空指派
    "required_start_time", "reminder_message", "reminder_minutes_before",
    "time_deposit", "is_active", "timed_mode", "deadline_time", "start_time",
    "duration_minutes", "pool_policy", "estimated_minutes", "difficulty",
    "content_mode", "content_brief",  # docs/15 R24
)


async def update_template(
    db: AsyncSession, *, family_id: str, template_id: str, payload: TaskTemplateUpdate,
) -> ScnTaskTemplate:
    """PATCH:部分更新;timed_mode 一致性对合并后的完整模板复验(422)。"""
    template = await get_family_template(db, template_id=template_id, family_id=family_id)

    data = payload.model_dump(exclude_unset=True)
    if "target_child_id" in data and data["target_child_id"] is not None:
        from app.services.task_service import _ensure_child

        await _ensure_child(db, family_id=family_id, child_id=data["target_child_id"])

    for field in _TEMPLATE_UPDATABLE_FIELDS:
        if field in data:
            setattr(template, field, data[field])

    # 对合并结果复验 timed_mode 一致性,防止 PATCH 分两步绕过创建期校验。
    try:
        validate_timed_mode(
            template.timed_mode,
            template.deadline_time,
            template.start_time,
            template.duration_minutes,
        )
    except ValueError as exc:
        await db.rollback()
        raise ValidationError(str(exc)) from exc

    triggers_changed = False
    if "triggers" in data:
        # model_dump 后是 dict;重新 model_validate 回对象,顺带补上 PATCH 路径的
        # 触发规则字段校验(kind 一致性,422),与创建口径一致。
        trigger_models = [
            TaskTriggerCreate.model_validate(t) for t in (data["triggers"] or [])
        ]
        template.triggers = _build_triggers(trigger_models)
        triggers_changed = True
    await db.commit()
    # updated_at 是 server 端 onupdate,flush 后处于 expired 态;
    # 不 refresh 的话 _to_read 同步读属性会触发隐式重载(MissingGreenlet)。
    await db.refresh(template)

    # 改规则后立即补一次生成(与创建同口径)。
    if triggers_changed:
        template_id = template.id  # 生成兜底的 rollback 会 expire 对象,先取普通值
        instance, action = await task_generator_service.generate_for_template(
            db, template, force=True,
        )
        # 兜底路径(exists)内部 rollback 会再次 expire 会话对象 —— 这里重新
        # refresh,保证 API 层 _to_read 同步读属性不再触发隐式重载。
        await db.refresh(template)
        log.info("template %s triggers updated, generation action=%s instance=%s",
                 template_id, action, getattr(instance, "id", None))
    return template


async def deprecate_template(
    db: AsyncSession, *, family_id: str, template_id: str, reason: str | None,
) -> ScnTaskTemplate:
    """废弃:停用 + 审计;既有实例不动,生成器此后跳过该模板。"""
    template = await get_family_template(db, template_id=template_id, family_id=family_id)
    template.is_active = False
    template.deprecated_at = utcnow()
    template.deprecated_reason = reason
    await db.commit()
    await db.refresh(template)  # 同 update_template:server onupdate 列需显式刷新
    return template


async def activate_template(
    db: AsyncSession, *, family_id: str, template_id: str,
) -> ScnTaskTemplate:
    """重新启用:清废弃标记,并立即补一次生成。"""
    template = await get_family_template(db, template_id=template_id, family_id=family_id)
    template.is_active = True
    template.deprecated_at = None
    template.deprecated_reason = None
    await db.commit()
    await db.refresh(template)  # 同 update_template:server onupdate 列需显式刷新
    template_id = template.id  # 生成兜底的 rollback 会 expire 对象,先取普通值
    instance, action = await task_generator_service.generate_for_template(
        db, template, force=True,
    )
    await db.refresh(template)  # 兜底路径(exists)rollback 后恢复可同步读
    log.info("template %s activated, generation action=%s instance=%s",
             template_id, action, getattr(instance, "id", None))
    return template


async def generate_instance_for_template(
    db: AsyncSession,
    *,
    family_id: str,
    template_id: str,
    payload: TaskGenerateRequest,
    today: date | None = None,
    now: datetime | None = None,
) -> tuple[ScnTaskInstance | None, str, bool]:
    """「选模板 → 生成」服务编排(DEV-50):校验 + 落库。

    返回 `(实例, 动作, overrides_applied)`。

    日期校验一律以家庭本地时区 `today_bj()` 为基准(不能用 UTC 日期:北京时间
    00:00-08:00 之间会差一天):
    - 缺省 = 今天;
    - `< 今天` → 422;
    - `> 今天 + MANUAL_GENERATE_MAX_AHEAD_DAYS` → 422。

    无激活赛季 / 模板已停用 → 409(见 `task_generator_service.manual_generate`)。
    """
    today = today or today_bj()
    template = await get_family_template(db, template_id=template_id, family_id=family_id)

    if template.deprecated_at is not None or not template.is_active:
        raise ConflictError("该模板已停用,无法生成任务")

    target_date = payload.target_date or today
    if target_date < today:
        raise ValidationError("目标日期不能早于今天")
    if target_date > today + timedelta(days=MANUAL_GENERATE_MAX_AHEAD_DAYS):
        raise ValidationError(f"目标日期最多提前 {MANUAL_GENERATE_MAX_AHEAD_DAYS} 天")

    if payload.target_child_id is not None:
        from app.services.task_service import _ensure_child

        await _ensure_child(db, family_id=family_id, child_id=payload.target_child_id)

    instance, action, applied = await task_generator_service.manual_generate(
        db,
        template,
        target_date=target_date,
        now=now,
        difficulty=payload.difficulty,
        time_deposit=payload.time_deposit,
        xp_reward=payload.xp_reward,
        target_child_id=payload.target_child_id,
    )
    if action == "no_season":
        # 实例 season_id 非空且"任务不跨赛季":没有激活赛季就有没有可归属的对象,
        # 没有中间态。转成 409 而不是让一个前端不认识的动作漏出去。
        raise ConflictError("当前没有进行中的赛季,无法生成任务")
    if action == "not_due":
        # 理论上已被上面的"模板已停用"守卫拦住;留一道防御,避免任何漏网的
        # 动作值流到前端(动作枚举只承诺 created/exists/rolled_forward/kept/
        # skipped_expired)。
        raise ConflictError("该模板当前不可生成任务")
    return instance, action, applied


# regenerate 的终结范围(Mars #2 / 产品拍板):只终结 AVAILABLE + IN_PROGRESS。
# PENDING_REVIEW 是孩子已提交待审核的成果,必须保留审核机会(仍可 approve/reject);
# 代价是待审核实例仍占用实例池槽位,存在时 generate 会返回 kept,本轮不新建实例
# (与 D1"同模板最多 1 条未消费"一致,审核完结后下个触发周期恢复生成)。
REGENERATE_TERMINAL_STATUSES = (TaskStatus.AVAILABLE, TaskStatus.IN_PROGRESS)


async def regenerate_template(
    db: AsyncSession, *, family_id: str, template_id: str,
) -> tuple[str, list[str], ScnTaskInstance | None, str]:
    """再生成:终结 AVAILABLE/IN_PROGRESS 实例(状态机语义同过期),随后尝试生成新实例。

    - PENDING_REVIEW 不终结(保留审核机会,见 REGENERATE_TERMINAL_STATUSES);
    - IN_PROGRESS 退全额押金,不计惩罚——regenerate 是家长侧发起的终结,
      孩子未违反任何约定(截止未必到),与 task_service.expire_overdue_tasks
      的"超时退 50%/扣罚 50%"(DEV-34 块 C+D,孩子错过截止)是两条口径,
      互不回退;
    - SELECT 带 with_for_update(Mars #3):防止与孩子接取/提交/家长审核并发时
      双花押金或覆盖状态。

    返回 (template_id, 终结的实例 id 列表, 新实例或 None, 生成动作);
    id 均为普通字符串 —— 生成兜底的 rollback 会 expire 会话对象,
    调用方不得在 generate 之后再同步读 ORM 对象属性。
    """
    template = await get_family_template(db, template_id=template_id, family_id=family_id)
    # DEV-50:无激活赛季时终结后也生不出新实例(实例必须有赛季归属)。先拦在
    # 终结**之前** —— 否则会把旧实例置 EXPIRED、释放槽位,却什么都生成不出来,
    # 留下一个"任务被清空"的半成品状态。
    if await task_generator_service.active_season_id(db, family_id) is None:
        raise ConflictError("当前没有进行中的赛季,无法重新生成任务")
    stmt = (
        select(ScnTaskInstance)
        .where(
            ScnTaskInstance.template_id == template.id,
            ScnTaskInstance.status.in_(REGENERATE_TERMINAL_STATUSES),
        )
        .with_for_update()
    )
    terminalized = list((await db.execute(stmt)).scalars().all())
    now = utcnow()
    for instance in terminalized:
        if instance.status == TaskStatus.IN_PROGRESS and instance.assignee_child_id:
            child = await db.get(SysChild, instance.assignee_child_id)
            if child is not None:
                deposit = instance.time_deposit  # 创建时已由 resolve_deposit 落库,无 or 10 兜底
                child.time_coin_balance += deposit
                await coin_service.record_transaction(
                    db,
                    child=child,
                    type=CoinTransactionType.TASK_REFUND,
                    amount=deposit,
                    task_instance_id=instance.id,
                    note="模板再生成终结任务退还押金",
                )
                instance.coin_delta = 0
        instance.status = TaskStatus.EXPIRED
        instance.expire_at = instance.expire_at or now
        # 释放实例池槽位:partial unique index 以 (template_id, generated_for_date)
        # 兜底同日幂等,终结后若不释放,同日再生成会撞索引回捞到旧 EXPIRED 行。
        instance.generated_for_date = None
    terminalized_ids = [i.id for i in terminalized]  # rollback 前先取普通值
    await db.commit()
    fresh, action = await task_generator_service.generate_for_template(
        db, template, force=True,
    )
    return template_id, terminalized_ids, fresh, action


async def delete_template(
    db: AsyncSession, *, family_id: str, template_id: str,
) -> None:
    """硬删:先删该模板全部实例与触发规则,再删模板行(同一事务)。

    Mars #4 / 产品拍板:存在 COMPLETED/EXPIRED 历史实例时拒绝(422),
    成长记录(含 proof/审核结论)是产品资产,不可硬删——引导走 deprecate。
    硬删仅在"无历史实例"时可用。
    """
    template = await get_family_template(db, template_id=template_id, family_id=family_id)
    instances = list(
        (await db.execute(
            select(ScnTaskInstance).where(ScnTaskInstance.template_id == template.id)
        )).scalars().all()
    )
    historical = [i for i in instances if i.status in (TaskStatus.COMPLETED, TaskStatus.EXPIRED)]
    if historical:
        raise ValidationError(
            f"该模板已有 {len(historical)} 条已完成/已过期实例(孩子的成长记录),"
            "不可硬删;如需停用请走 deprecate"
        )
    for instance in instances:
        await db.delete(instance)
    await db.delete(template)
    await db.commit()


async def list_templates(
    db: AsyncSession, *, family_id: str, season_id: str | None = None,
    is_active: bool | None = None, template_type: str | None = None,
) -> list[ScnTaskTemplate]:
    stmt = (
        select(ScnTaskTemplate)
        .where(ScnTaskTemplate.family_id == family_id)
        .options(selectinload(ScnTaskTemplate.triggers))
        .order_by(ScnTaskTemplate.created_at.desc())
    )
    if season_id is not None:
        stmt = stmt.where(ScnTaskTemplate.season_id == season_id)
    if is_active is not None:
        stmt = stmt.where(ScnTaskTemplate.is_active.is_(is_active))
    if template_type is not None:
        stmt = stmt.where(ScnTaskTemplate.type == template_type)
    return list((await db.execute(stmt)).scalars().all())


# ---- 模板库(docs/06 §2) ----


async def list_library(
    db: AsyncSession, *, family_id: str, category: str | None = None,
    keyword: str | None = None, favorites_only: bool = False,
) -> tuple[list[ScnTaskTemplateLibrary], set[str]]:
    """系统库条目 + 本家庭自建条目(不含收藏克隆行);返回 (条目, 本家庭收藏的原始 id 集)。

    收藏实现:收藏行是本家庭名下的一条库克隆(meta.favorite_of 指向原条目),
    不新增表;favorites_only 时直接返回收藏行自身。
    """
    favorites = list(
        (await db.execute(
            select(ScnTaskTemplateLibrary).where(
                ScnTaskTemplateLibrary.family_id == family_id,
                ScnTaskTemplateLibrary.meta.op("->>")(_FAVORITE_OF_KEY).is_not(None),
            )
        )).scalars().all()
    )
    favorite_of_ids = {f.meta[_FAVORITE_OF_KEY] for f in favorites}

    if favorites_only:
        return favorites, favorite_of_ids

    stmt = select(ScnTaskTemplateLibrary).where(
        ScnTaskTemplateLibrary.is_active.is_(True),
        ScnTaskTemplateLibrary.meta.op("->>")(_FAVORITE_OF_KEY).is_(None),
    ).order_by(ScnTaskTemplateLibrary.created_at.desc())
    rows = list((await db.execute(stmt)).scalars().all())
    # 家庭可见范围:系统预置(family_id IS NULL)+ 本家庭自建。
    rows = [r for r in rows if r.family_id is None or r.family_id == family_id]
    if category is not None:
        rows = [r for r in rows if _enum_value(r.category) == category]
    if keyword:
        kw = keyword.strip()
        rows = [r for r in rows if kw in r.title or kw in r.description]
    return rows, favorite_of_ids


async def get_library_entry(
    db: AsyncSession, entry_id: str,
) -> ScnTaskTemplateLibrary:
    entry = await db.get(ScnTaskTemplateLibrary, entry_id)
    if not entry or not entry.is_active:
        raise NotFoundError(f"模板库条目 {entry_id} 不存在")
    return entry


async def toggle_favorite(
    db: AsyncSession, *, family_id: str, entry_id: str,
) -> bool:
    """收藏/取消收藏开关;返回切换后的收藏状态。"""
    entry = await get_library_entry(db, entry_id)
    # limit(1)(Mars #6):无唯一索引时快速双击可能插入重复收藏行,
    # 取一行而非 scalar_one,避免 MultipleResultsFound 500;唯一索引待后续迁移。
    existing = (
        await db.execute(
            select(ScnTaskTemplateLibrary)
            .where(
                ScnTaskTemplateLibrary.family_id == family_id,
                ScnTaskTemplateLibrary.meta.op("->>")(_FAVORITE_OF_KEY) == entry.id,
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing is not None:
        await db.delete(existing)
        await db.commit()
        return False
    favorite = ScnTaskTemplateLibrary(
        family_id=family_id,
        category=entry.category,
        tags=entry.tags,
        title=entry.title,
        description=entry.description,
        suggested_xp=entry.suggested_xp,
        suggested_time_deposit=entry.suggested_time_deposit,
        suggested_type=entry.suggested_type,
        meta={_FAVORITE_OF_KEY: entry.id},
        is_active=True,
    )
    db.add(favorite)
    await db.commit()
    return True


async def apply_library_entry(
    db: AsyncSession, *, family_id: str, creator_id: str,
    entry_id: str, season_id: str | None = None, target_child_id: str | None = None,
) -> ScnTaskTemplate:
    """套用:用 suggested_* 播种一个新模板(挂默认触发规则),并立即跑一次生成。

    `season_id` 可选(DEV-50 同源口径:模板不绑赛季),与 `POST /scn/task-templates`
    一致 —— 否则套用路径会继续造出被硬绑在单赛季上的模板。
    """
    if season_id is not None:
        await _ensure_season(db, family_id=family_id, season_id=season_id)
    entry = await get_library_entry(db, entry_id)
    payload = TaskTemplateCreate(
        season_id=season_id,
        library_id=entry.id,
        category=entry.category,
        title=entry.title,
        description=entry.description,
        xp_reward=entry.suggested_xp,
        type=entry.suggested_type,
        target_child_id=target_child_id,
        time_deposit=entry.suggested_time_deposit,
        timed_mode=TimedMode.NONE,
        pool_policy=PoolPolicy.REUSE_UNTIL_CONSUMED,
    )
    return await create_template(db, family_id=family_id, creator_id=creator_id, payload=payload)
