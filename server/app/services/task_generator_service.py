"""任务实例生成器(docs/12 块 A/B,DEV-35)。

职责:
- `due_templates(today, now)`: 找出"当日到期"的模板 —— 任一 active 触发规则命中
  (DAILY/WEEKDAYS/MONTHLY/CRON 匹配 today、generate_at 已过、日期在 [starts_on, ends_on])。
- `generate_for_template(...)`: 对单个模板幂等生成/顺延实例(决策 D1/D2):
  - 已有未消费实例且归属今日 -> 不动(同触发日跑两次/多触发同日命中都只有 1 条);
  - 未消费 AVAILABLE 且 REUSE_UNTIL_CONSUMED -> roll_forward 顺延到今日并重算时间窗;
  - 未消费 IN_PROGRESS/PENDING_REVIEW -> 保持,不新增;
  - 无未消费实例(昨日已 COMPLETED,或昨日 EXPIRED 周期已终结)-> 生成新实例。
- 并发兜底:插入撞 `UNIQUE(template_id, generated_for_date)` 抛 IntegrityError,
  回滚后取回既有行,不做任何锁定。

消费语义(块 B):
    AVAILABLE      未消费 -> 顺延
    IN_PROGRESS    未消费 -> 保持,不新增
    PENDING_REVIEW 未消费 -> 保持,不新增
    COMPLETED      已消费 -> 下个触发周期生成新实例
    EXPIRED        周期已终结 -> 不顺延,下个周期生成新实例

自然日与生成时刻统一锚定家庭本地时区 Asia/Shanghai(见 common/timeutil)。
"""
from __future__ import annotations

import calendar
import logging
from datetime import date, datetime, time, timedelta

from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.common.exceptions import ConflictError
from app.common.timeutil import BJ_TZ, now_bj, today_bj, utcnow
from app.config import settings
from app.models.enums import (
    ContentMode,
    ContentSource,
    PoolPolicy,
    TaskStatus,
    TimedMode,
    TriggerKind,
)
from app.models.scn_season import ScnSeason
from app.models.scn_task_instance import ScnTaskInstance
from app.models.scn_task_template import ScnTaskTemplate
from app.models.scn_task_template_trigger import ScnTaskTemplateTrigger
from app.models.sys_child import SysChild
from app.services import ai_service, coin_service, season_service

log = logging.getLogger(__name__)

# 未消费状态:生成器眼中"还占着实例池"的状态(决策 D2)。
UNCONSUMED_STATUSES = (TaskStatus.AVAILABLE, TaskStatus.IN_PROGRESS, TaskStatus.PENDING_REVIEW)


def _kind(trigger: ScnTaskTemplateTrigger) -> str:
    value = trigger.kind
    return value.value if hasattr(value, "value") else str(value)


def _cron_matches(cron_expr: str, day: date) -> bool:
    """5 段 cron 是否在 day(北京时区)有触发时刻。

    借 APScheduler CronTrigger 计算当日 00:00 之后的下一次触发,
    落在 day 内即命中;表达式本身在 schema 层已校验过格式。
    注意:day_of_week 段取 APScheduler 语义(0=周一..6=周日,非 Unix 0=周日),
    校验与匹配同源,不会出现口径漂移。
    """
    start = datetime.combine(day, time.min, tzinfo=BJ_TZ)
    try:
        trigger = CronTrigger.from_crontab(cron_expr, timezone=BJ_TZ)
    except ValueError:
        return False
    nxt = trigger.get_next_fire_time(None, start)
    return nxt is not None and nxt.astimezone(BJ_TZ).date() == day


def trigger_matches_day(trigger: ScnTaskTemplateTrigger, day: date) -> bool:
    """单条规则的日期部分是否命中 day(不含 generate_at 时刻与生效区间判断)。"""
    kind = _kind(trigger)
    if kind == TriggerKind.DAILY.value:
        return True
    if kind == TriggerKind.WEEKDAYS.value:
        weekdays = trigger.weekdays or []
        return day.weekday() in weekdays  # 0=周一..6=周日,与字段口径一致
    if kind == TriggerKind.MONTHLY.value:
        if trigger.day_of_month is None:
            return False
        # 月末不足取当月最后一天:31 在 2 月命中 28/29。
        effective = min(trigger.day_of_month, calendar.monthrange(day.year, day.month)[1])
        return day.day == effective
    if kind == TriggerKind.CRON.value:
        return bool(trigger.cron_expr) and _cron_matches(trigger.cron_expr, day)
    if kind == TriggerKind.ONCE.value:
        return trigger.starts_on is not None and day == trigger.starts_on
    return False


def trigger_due(
    trigger: ScnTaskTemplateTrigger, *, today: date, now: datetime | None = None,
) -> bool:
    """规则是否已到期(可生成):active + 命中 today + generate_at 已过 + 在生效区间。"""
    if not trigger.is_active:
        return False
    if trigger.starts_on is not None and today < trigger.starts_on:
        return False
    if trigger.ends_on is not None and today > trigger.ends_on:
        return False
    if not trigger_matches_day(trigger, today):
        return False
    now = now or now_bj()
    if now.tzinfo is None:
        now = now.replace(tzinfo=BJ_TZ)
    else:
        now = now.astimezone(BJ_TZ)
    return now.time() >= (trigger.generate_at or time(0, 0))


async def due_templates(
    db: AsyncSession, *, today: date | None = None, now: datetime | None = None,
) -> list[ScnTaskTemplate]:
    """所有"今日到期待生成"的模板:启用中、未废弃、任一规则到期。"""
    today = today or today_bj()
    stmt = (
        select(ScnTaskTemplate)
        .where(
            ScnTaskTemplate.is_active.is_(True),
            ScnTaskTemplate.deprecated_at.is_(None),
        )
        .options(selectinload(ScnTaskTemplate.triggers))
    )
    templates = list((await db.execute(stmt)).scalars().all())
    return [
        t for t in templates
        if any(trigger_due(g, today=today, now=now) for g in t.triggers)
    ]


def _mode_value(mode) -> str:
    return mode.value if hasattr(mode, "value") else str(mode)


def compute_expire_at(template: ScnTaskTemplate, day: date) -> datetime | None:
    """限时任务的过期时刻(北京时区);非限时(NONE)恒为 NULL。

    - DEADLINE  -> day @ deadline_time
    - DURATION  -> day @ (start_time + duration_minutes)
    """
    mode_value = _mode_value(template.timed_mode)
    if mode_value == TimedMode.NONE.value:
        return None
    if mode_value == TimedMode.DEADLINE.value:
        if template.deadline_time is None:
            return None
        return datetime.combine(day, template.deadline_time, tzinfo=BJ_TZ)
    if mode_value == TimedMode.DURATION.value:
        if template.start_time is None or not template.duration_minutes:
            return None
        start_dt = datetime.combine(day, template.start_time, tzinfo=BJ_TZ)
        return start_dt + timedelta(minutes=template.duration_minutes)
    return None


async def active_season_id(db: AsyncSession, family_id: str) -> str | None:
    """家庭当前激活赛季的 id;无则 None。

    DEV-50「模板可跨赛季,任务不跨赛季」:模板已与赛季解绑,实例的实际赛季取
    **生成当时**的激活赛季 —— 叙事背景(叙事主题)同理。无激活赛季时实例没有
    可归属的对象(实例 `season_id` 仍是 NOT NULL),自动生成跳过、手动生成 409。
    """
    season = await season_service.get_active_season(db, family_id)
    return season.id if season is not None else None


async def _latest_unconsumed(
    db: AsyncSession, template_id: str, *, today: date,
) -> ScnTaskInstance | None:
    """模板最近一条**在池内**的未消费实例;无则 None。

    池口径(DEV-50):`generated_for_date IS NULL OR <= today`。**未来日期的实例
    一律视为「已排期」,不入池、不占槽、不被顺延** —— 家长可以为明天预生成,
    既不会占掉今天的槽位,也不会被夜间作业提前拉回今天。D1(同一模板同一时刻
    最多 1 条未消费实例)语义不变,只是"池"不再包含未来实例。

    `IS NULL` 保留旧 `POST /scn/tasks` 一次性路径的存量行(无逻辑日),口径同前。
    """
    stmt = (
        select(ScnTaskInstance)
        .where(
            ScnTaskInstance.template_id == template_id,
            ScnTaskInstance.status.in_(UNCONSUMED_STATUSES),
            or_(
                ScnTaskInstance.generated_for_date.is_(None),
                ScnTaskInstance.generated_for_date <= today,
            ),
        )
        .order_by(
            ScnTaskInstance.generated_for_date.desc().nulls_last(),
            ScnTaskInstance.created_at.desc(),
        )
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def _get_instance_for_date(
    db: AsyncSession, template_id: str, day: date,
) -> ScnTaskInstance | None:
    stmt = select(ScnTaskInstance).where(
        ScnTaskInstance.template_id == template_id,
        ScnTaskInstance.generated_for_date == day,
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def _load_content_context(
    db: AsyncSession, template: ScnTaskTemplate, *, season_id: str | None,
) -> tuple[str, int]:
    """叙事生成的上下文要素(docs/15 R18):返回 (赛季主题, 孩子等级)。

    `season_id` 是**生成当时**的激活赛季(DEV-50),不是模板的来源赛季 —— 业主
    口径是"生成任务时结合**当季**背景",取模板的旧赛季会直接违背它。
    """
    topic = ""
    if season_id is not None:
        season = await db.get(ScnSeason, season_id)
        if season is not None:
            topic = season.narrative_context or ""
    child_level = 1
    if template.target_child_id is not None:
        child = await db.get(SysChild, template.target_child_id)
        if child is not None:
            child_level = child.level
    return topic, child_level


async def _prepare_content(
    db: AsyncSession, template: ScnTaskTemplate, *, day: date, season_id: str | None,
) -> tuple[str | None, str, dict | None]:
    """按模板 content_mode 准备实例叙事内容(docs/15 §6)。

    返回 (lore_snippet, content_source, generation_meta) —— 全部普通值,
    不持有 ORM 对象:调用方插入撞索引时整事务 rollback 会 expire 会话内
    全部对象(R10,叙事必须是普通字符串)。

    - STATIC        -> 直接复制模板 lore_snippet,标 TEMPLATE(R7);
    - LLM 且开关闭  -> 不调 LLM,落模板文本标 FALLBACK(R21);
    - LLM 且开关开  -> 调 ai_service.generate_task_narrative 一次(R8);
      任何失败(能力未启用/未配置、HTTP、超时、非法 JSON、空文本、超长)
      落模板文本标 FALLBACK,不向上抛(R12/R13)。

    LLM 与 FALLBACK 结果各打 1 行日志(模板 id/目标日期/content_source/耗时,
    不含 API key 与提示词全文,R27)。
    """
    mode = _mode_value(template.content_mode)
    if mode != ContentMode.LLM.value:
        return template.lore_snippet, ContentSource.TEMPLATE.value, None

    cfg = settings.task_content
    template_id = template.id  # 后续路径可能 rollback,先取普通值
    if not cfg.llm_enabled:
        meta = {
            "model": settings.ai.llm.model,
            "prompt_hash": None, "tokens": None, "elapsed_ms": 0,
            "error": "LLMDisabled",
        }
        log.info(
            "task content: template=%s date=%s content_source=FALLBACK elapsed_ms=0",
            template_id, day,
        )
        return template.lore_snippet, ContentSource.FALLBACK.value, meta

    brief = template.content_brief or template.description or ""  # R19:空回落 description
    topic, child_level = "", 1
    try:
        # 上下文加载纳入同一 try(Mars 🟡1):赛季/孩子查询失败也回落 FALLBACK,
        # 不让实例创建失败(R13)。失败时保留默认值 ("", 1) 继续生成。
        topic, child_level = await _load_content_context(db, template, season_id=season_id)
        narrative, meta = await ai_service.generate_task_narrative(
            content_brief=brief,
            topic=topic,
            category=_mode_value(template.category) if template.category else None,
            child_level=child_level,
            is_weekend=day.weekday() >= 5,
            task_type=_mode_value(template.type),
            timeout_seconds=cfg.llm_timeout_seconds,
            max_narrative_chars=cfg.max_narrative_chars,
        )
        log.info(
            "task content: template=%s date=%s content_source=LLM elapsed_ms=%s",
            template_id, day, meta.get("elapsed_ms"),
        )
        return narrative, ContentSource.LLM.value, meta
    except Exception as exc:  # noqa: BLE001 - R13:LLM 任何失败都不阻断实例创建
        # meta 由 ai_service 备好(含底层错误类名);非 TaskNarrativeError 的
        # 意外异常(含上下文加载失败)兜底补错误类名与模型名。R14:FALLBACK
        # 必须留错误类名。
        meta = dict(getattr(exc, "meta", None) or {})
        meta.setdefault("error", type(exc).__name__)
        meta.setdefault("model", settings.ai.llm.model)
        meta.setdefault("elapsed_ms", 0)
        log.warning(
            "task content: template=%s date=%s content_source=FALLBACK "
            "elapsed_ms=%s error=%s",
            template_id, day, meta.get("elapsed_ms"), type(exc).__name__,
        )
        return template.lore_snippet, ContentSource.FALLBACK.value, meta


async def _insert_instance(
    db: AsyncSession, template: ScnTaskTemplate, day: date,
    *,
    season_id: str,
    lore_snippet: str | None = None,
    content_source: str = ContentSource.TEMPLATE.value,
    generation_meta: dict | None = None,
    difficulty: int | None = None,
    xp_reward: int | None = None,
    time_deposit: int | None = None,
    target_child_id: str | None = None,
) -> tuple[ScnTaskInstance, bool]:
    """插入目标日实例;撞唯一索引(并发兜底)时回滚并取回既有行。

    lore_snippet/content_source/generation_meta 由调用方在写库前备好
    (LLM 必须在写库之前调用,叙事存普通字符串,R10)。缺省即 STATIC
    口径:复制模板 lore_snippet、标 TEMPLATE。

    `season_id` 由调用方解析后传入(DEV-50:生成当时的**激活赛季**,不再是
    `template.season_id` —— 模板已与赛季解绑)。

    三个数值字段是**快照**(DEV-50):`None` = 生成时取模板当前值;非 None =
    本次生成显式覆盖(「选模板 → 生成」表单可带覆盖值)。三者语义同构,都由
    这里一次落库,之后可经 `PATCH /scn/task-instances/{id}` 独立调整。

    返回 (实例, 是否新建)。兜底取回既有行时 created=False(可能是并发方
    刚插入的 AVAILABLE 行,也可能是当日已消费的 COMPLETED/EXPIRED 行),
    调用方据此返回诚实的动作而非 "created"。
    """
    template_id = template.id
    family_id = template.family_id
    creator_account_id = template.creator_account_id
    expire_at = compute_expire_at(template, day)
    instance = ScnTaskInstance(
        family_id=family_id,
        season_id=season_id,
        template_id=template_id,
        creator_account_id=creator_account_id,
        target_child_id=target_child_id or template.target_child_id,
        title=template.title,
        description=template.description,
        lore_snippet=template.lore_snippet if lore_snippet is None else lore_snippet,
        xp_reward=template.xp_reward if xp_reward is None else xp_reward,
        # 难度快照:生成即定值,审批算 XP 读本列。**不回落模板** —— 否则改模板
        # 会移动未结算实例的 XP,正是 docs/15 §12 P2 要防的追溯。
        difficulty=template.difficulty if difficulty is None else difficulty,
        status=TaskStatus.AVAILABLE,
        deadline=expire_at,  # 限时任务 deadline 与过期时刻同源;非限时恒 NULL
        expire_at=expire_at,
        generated_for_date=day,
        time_deposit=template.time_deposit if time_deposit is None else time_deposit,
        content_source=content_source,
        generation_meta=generation_meta,
    )
    db.add(instance)
    try:
        await db.flush()
    except IntegrityError:
        # 真实并发/当日已消费兜底:另一行已持有 (template_id, day)。
        # 注:SAVEPOINT(begin_nested)在 asyncpg 下救不了外层事务(语句失败仍会
        # PendingRollback),只能整事务 rollback —— 它会 expire 会话内全部对象,
        # 因此 template_id 等属性必须在插入前先取为普通值;调用方在兜底动作
        # (exists)返回后如需同步读模板属性,须自行 db.refresh(template)。
        await db.rollback()
        existing = await _get_instance_for_date(db, template_id, day)
        if existing is None:
            raise ConflictError(
                f"任务实例并发插入冲突且无法取回: template={template_id} day={day}"
            )
        return existing, False
    return instance, True


async def generate_for_template(
    db: AsyncSession,
    template: ScnTaskTemplate,
    *,
    today: date | None = None,
    now: datetime | None = None,
    force: bool = False,
    manual: bool = False,
    difficulty: int | None = None,
    time_deposit: int | None = None,
    xp_reward: int | None = None,
    target_child_id: str | None = None,
) -> tuple[ScnTaskInstance | None, str]:
    """对单个模板执行一次生成;返回 (实例, 动作)。

    动作: created / rolled_forward / kept / exists / not_due /
    skipped_expired / no_season。
    force=True 跳过 generate_at 时刻检查(模板创建/改规则/激活后立即补一次生成),
    仍要求有规则命中 today 且在生效区间。
    manual=True(DEV-50) **完全豁免触发规则** —— 业主口径是"选模板 → 生成"这一
    家长显式动作,不该被日历规则限制(否则"每周一"的模板周三手动也生成不了)。
    手动生成走 `manual_generate`(还要支持目标日期与覆盖值),这里是自动路径。

    无激活赛季时返回 no_season:实例 season_id 非空且**任务不跨赛季**,没有
    可归属的对象。自动路径跳过(不阻断整轮),手动路径由调用方转 409。
    """
    today = today or today_bj()
    now = now or now_bj()

    if template.deprecated_at is not None or not template.is_active:
        return None, "not_due"
    if manual:
        due = True
    else:
        due = any(
            trigger_due(g, today=today, now=now)
            or (
                force
                and g.is_active
                and (g.starts_on is None or today >= g.starts_on)
                and (g.ends_on is None or today <= g.ends_on)
                and trigger_matches_day(g, today)
            )
            for g in template.triggers
        )
    if not due:
        return None, "not_due"

    # DEV-50:实例赛季取"生成当时的激活赛季";先取普通值(后续 rollback 会
    # expire 会话内对象)。
    season_id = await active_season_id(db, template.family_id)
    if season_id is None:
        return None, "no_season"

    existing = await _latest_unconsumed(db, template.id, today=today)
    if existing is not None:
        if existing.generated_for_date == today:
            # 同触发日重复执行 / 多组规则同日命中:按模板去重,恒 1 条。
            return existing, "exists"
        if existing.status == TaskStatus.AVAILABLE and (
            template.pool_policy == PoolPolicy.REUSE_UNTIL_CONSUMED
        ):
            # roll_forward(决策 D1):未消费实例跨天顺延 —— 日期前滚到今天,
            # 按今天窗口重算 expire_at,既不被过期 job 误杀,又堵死同日重复生成。
            existing.generated_for_date = today
            expire_at = compute_expire_at(template, today)
            existing.expire_at = expire_at
            existing.deadline = expire_at
            template_id = template.id  # rollback 会 expire 对象,先取普通值
            try:
                await db.commit()
            except IntegrityError:
                # 与 _insert_instance 同级兜底(Mars #5):当前调用链下不可达
                # (旧实例路径不写 generated_for_date;regenerate 先释放槽位),
                # 防未来路径(NEW_EACH_PERIOD/数据回填)在同模板已有当日行时裸撞索引。
                await db.rollback()
                winner = await _get_instance_for_date(db, template_id, today)
                if winner is None:
                    raise ConflictError(
                        f"roll_forward 并发冲突且无法取回: template={template_id} day={today}"
                    )
                return winner, "exists"
            return existing, "rolled_forward"
        # IN_PROGRESS / PENDING_REVIEW:孩子手里,保持不动;NEW_EACH_PERIOD 本轮不默认。
        return existing, "kept"

    # 限时任务"生成即过期"守卫:生成时刻已过今日截止(如 21:00 创建 DEADLINE 20:00
    # 的模板后立即补生成),产物会在 5 分钟内被过期 job 判死,直接跳过当日生成。
    expire_at = compute_expire_at(template, today)
    if expire_at is not None and expire_at <= now:
        return None, "skipped_expired"

    # docs/15:叙事内容在写库之前准备(LLM 可能在此发生,普通字符串带回)。
    # 仅新建路径到这里 —— rolled_forward/exists/kept/not_due/skipped_expired
    # 均不调 LLM(R11),顺延任务保留首次生成的叙事。
    lore_snippet, content_source, generation_meta = await _prepare_content(
        db, template, day=today, season_id=season_id,
    )
    instance, created = await _insert_instance(
        db, template, today,
        season_id=season_id,
        lore_snippet=lore_snippet,
        content_source=content_source,
        generation_meta=generation_meta,
        difficulty=difficulty,
        time_deposit=time_deposit,
        xp_reward=xp_reward,
        target_child_id=target_child_id,
    )
    await db.commit()
    if not created:
        # 兜底回捞到当日既有行(并发方的 AVAILABLE,或当日已消费的
        # COMPLETED/EXPIRED)——如实报告"已存在",不冒充新建。
        return instance, "exists"
    return instance, "created"


async def manual_generate(
    db: AsyncSession,
    template: ScnTaskTemplate,
    *,
    target_date: date,
    now: datetime | None = None,
    difficulty: int | None = None,
    time_deposit: int | None = None,
    xp_reward: int | None = None,
    target_child_id: str | None = None,
) -> tuple[ScnTaskInstance | None, str, bool]:
    """「选模板 → 生成」的落库路径(DEV-50)。

    与自动路径的差异:**豁免触发规则**、目标日期由调用方校验后传入(≥ 今天)、
    可携带三个快照字段的覆盖值。

    返回 `(实例, 动作, overrides_applied)`。动作沿用自动路径的枚举。
    `overrides_applied` **只在 `created` 时为 True** —— 其余动作都是"复用既有
    实例",按前端预检文案「该日期已有任务实例,将直接使用该实例(不覆盖、
    不重建)」不对既有实例写入。显式回传是为了避免"传了覆盖值却被静默丢弃",
    前端据此把用户引导到 `PATCH /scn/task-instances/{id}`。

    `time_deposit` 覆盖值走与模板创建同源的 `coin_service.resolve_deposit`
    (显式值 → clamp 类型区间 → 封顶当日配额),`day` 取**目标日期** —— 配额按
    星期几不同,用今天的配额去卡周末会算错。
    """
    now = now or now_bj()
    today = today_bj()

    if time_deposit is not None:
        time_deposit = await coin_service.resolve_deposit(
            db,
            family_id=template.family_id,
            task_type=template.type,
            explicit_deposit=time_deposit,
            day=target_date,
        )

    if target_date == today:
        # 目标日 == 今天:直接复用自动路径的全部池语义(顺延/保持/生成即过期),
        # 只是豁免触发规则。一处实现,避免两份池逻辑漂移。
        instance, action = await generate_for_template(
            db, template, today=today, now=now, manual=True,
            difficulty=difficulty, time_deposit=time_deposit,
            xp_reward=xp_reward, target_child_id=target_child_id,
        )
        return instance, action, action == "created"

    # 目标日 > 今天(未来):**不查池**。未来实例不入池、不占槽(池谓词见
    # `_latest_unconsumed`),所以"为明天预生成"不会被今天的在途任务挡住,
    # 也不会把今天的任务顺延到明天。
    if template.deprecated_at is not None or not template.is_active:
        return None, "not_due", False
    season_id = await active_season_id(db, template.family_id)
    if season_id is None:
        return None, "no_season", False

    existing = await _get_instance_for_date(db, template.id, target_date)
    if existing is not None:
        return existing, "exists", False

    # 未来日期的限时任务若截止时刻已过(如把 20:00 截止的模板生成到若干天前,
    # 或目标日 == 今天但已过点)不允许出条 —— 与自动路径同一守卫。
    expire_at = compute_expire_at(template, target_date)
    if expire_at is not None and expire_at <= now:
        return None, "skipped_expired", False

    lore_snippet, content_source, generation_meta = await _prepare_content(
        db, template, day=target_date, season_id=season_id,
    )
    instance, created = await _insert_instance(
        db, template, target_date,
        season_id=season_id,
        lore_snippet=lore_snippet,
        content_source=content_source,
        generation_meta=generation_meta,
        difficulty=difficulty,
        time_deposit=time_deposit,
        xp_reward=xp_reward,
        target_child_id=target_child_id,
    )
    await db.commit()
    if not created:
        return instance, "exists", False
    return instance, "created", True


async def run_generation(
    db: AsyncSession, *, today: date | None = None, now: datetime | None = None,
) -> dict[str, int]:
    """全量跑一轮生成(定时任务 00:10 / 手动触发)。返回各动作计数。

    逐模板隔离(Fabio 冒烟 P1-1):单模板的生成兜底会整事务 rollback 并
    expire 会话内全部对象(如当日已 COMPLETED 模板撞索引回捞的 exists 路径),
    直接复用循环外的 ORM 对象会让下一模板的同步属性访问触发隐式重载
    (MissingGreenlet)并中断整轮 —— 当天任务板空窗。因此:
    - id 在循环前预取为普通值,日志只用预取值;
    - 每个模板进循环后重新 SELECT(带 selectin triggers),不依赖可能已被
      expire 的对象;单模板异常 rollback 后 continue,计入 stats.errors。
    """
    today = today or today_bj()
    stats = {
        "created": 0, "rolled_forward": 0, "kept": 0, "exists": 0,
        "not_due": 0, "skipped_expired": 0, "errors": 0,
        # DEV-50:该家庭没有激活赛季 —— 实例无可归属赛季(任务不跨赛季),跳过。
        "no_season": 0,
        "llm_generated": 0, "fallback": 0,  # docs/15 R27
    }
    due = await due_templates(db, today=today, now=now)
    plan = [t.id for t in due]  # 预取普通值:后续 rollback 会使 ORM 对象失效
    for template_id in plan:
        try:
            stmt = (
                select(ScnTaskTemplate)
                .where(ScnTaskTemplate.id == template_id)
                .options(selectinload(ScnTaskTemplate.triggers))
            )
            template = (await db.execute(stmt)).scalar_one_or_none()
            if template is None:
                continue
            _instance, action = await generate_for_template(db, template, today=today, now=now)
            stats[action] = stats.get(action, 0) + 1
            if action == "created" and _instance is not None:
                # 新建实例按叙事来源计数(docs/15 R27);顺延/保留的实例沿用
                # 首次生成的叙事,不计入本轮。
                source = _mode_value(_instance.content_source)
                if source == ContentSource.LLM.value:
                    stats["llm_generated"] += 1
                elif source == ContentSource.FALLBACK.value:
                    stats["fallback"] += 1
        except Exception:
            # 单模板失败不阻断整轮;生产由日志告警跟进。
            stats["errors"] += 1
            log.exception("generate_for_template failed, template=%s", template_id)
            await db.rollback()
    return stats


# __all__ 与 utcnow 重导出说明:utcnow 供调度器/测试构造 aware 时刻,不参与自然日判定。
__all__ = [
    "UNCONSUMED_STATUSES",
    "active_season_id",
    "compute_expire_at",
    "due_templates",
    "generate_for_template",
    "manual_generate",
    "run_generation",
    "trigger_due",
    "trigger_matches_day",
    "utcnow",
]
