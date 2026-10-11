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
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.common.exceptions import ConflictError
from app.common.timeutil import BJ_TZ, now_bj, today_bj, utcnow
from app.models.enums import PoolPolicy, TaskStatus, TimedMode, TriggerKind
from app.models.scn_task_instance import ScnTaskInstance
from app.models.scn_task_template import ScnTaskTemplate
from app.models.scn_task_template_trigger import ScnTaskTemplateTrigger

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


async def _latest_unconsumed(
    db: AsyncSession, template_id: str,
) -> ScnTaskInstance | None:
    """模板最近一条未消费实例;无则 None。"""
    stmt = (
        select(ScnTaskInstance)
        .where(
            ScnTaskInstance.template_id == template_id,
            ScnTaskInstance.status.in_(UNCONSUMED_STATUSES),
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


async def _insert_instance(
    db: AsyncSession, template: ScnTaskTemplate, day: date,
) -> ScnTaskInstance:
    """插入当日实例;撞唯一索引(并发兜底)时回滚并取回既有行。

    注意:
    - 回滚会丢弃当前事务中未提交的其它改动,调用方须保证
      在模板改动 commit 之后再进入本函数;
    - rollback 会 expire 会话内全部对象,故 template_id 等属性必须在
      插入前先取为普通值,否则兜底路径上的属性访问会触发隐式重载。
    """
    template_id = template.id
    family_id = template.family_id
    season_id = template.season_id
    creator_account_id = template.creator_account_id
    target_child_id = template.target_child_id
    expire_at = compute_expire_at(template, day)
    instance = ScnTaskInstance(
        family_id=family_id,
        season_id=season_id,
        template_id=template_id,
        creator_account_id=creator_account_id,
        target_child_id=target_child_id,
        title=template.title,
        description=template.description,
        lore_snippet=template.lore_snippet,
        xp_reward=template.xp_reward,
        status=TaskStatus.AVAILABLE,
        deadline=expire_at,  # 限时任务 deadline 与过期时刻同源;非限时恒 NULL
        expire_at=expire_at,
        generated_for_date=day,
        time_deposit=template.time_deposit,
    )
    db.add(instance)
    try:
        await db.flush()
    except IntegrityError:
        # 真实并发兜底:另一个生成器/请求已插入同 (template_id, day) 行。
        await db.rollback()
        existing = await _get_instance_for_date(db, template_id, day)
        if existing is None:
            raise ConflictError(
                f"任务实例并发插入冲突且无法取回: template={template_id} day={day}"
            )
        return existing
    return instance


async def generate_for_template(
    db: AsyncSession,
    template: ScnTaskTemplate,
    *,
    today: date | None = None,
    now: datetime | None = None,
    force: bool = False,
) -> tuple[ScnTaskInstance | None, str]:
    """对单个模板执行一次生成;返回 (实例, 动作)。

    动作: created / rolled_forward / kept / exists / not_due。
    force=True 跳过 generate_at 时刻检查(模板创建/改规则/激活后立即补一次生成),
    仍要求有规则命中 today 且在生效区间。
    """
    today = today or today_bj()
    now = now or now_bj()

    if template.deprecated_at is not None or not template.is_active:
        return None, "not_due"
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

    existing = await _latest_unconsumed(db, template.id)
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
            await db.commit()
            return existing, "rolled_forward"
        # IN_PROGRESS / PENDING_REVIEW:孩子手里,保持不动;NEW_EACH_PERIOD 本轮不默认。
        return existing, "kept"

    instance = await _insert_instance(db, template, today)
    await db.commit()
    return instance, "created"


async def run_generation(
    db: AsyncSession, *, today: date | None = None, now: datetime | None = None,
) -> dict[str, int]:
    """全量跑一轮生成(定时任务 00:10 / 手动触发)。返回各动作计数。"""
    today = today or today_bj()
    stats = {"created": 0, "rolled_forward": 0, "kept": 0, "exists": 0, "not_due": 0, "errors": 0}
    templates = await due_templates(db, today=today, now=now)
    for template in templates:
        try:
            _instance, action = await generate_for_template(db, template, today=today, now=now)
            stats[action] = stats.get(action, 0) + 1
        except Exception:
            # 单模板失败不阻断整轮;生产由日志告警跟进。
            stats["errors"] += 1
            log.exception("generate_for_template failed, template=%s", template.id)
            await db.rollback()
    return stats


# __all__ 与 utcnow 重导出说明:utcnow 供调度器/测试构造 aware 时刻,不参与自然日判定。
__all__ = [
    "UNCONSUMED_STATUSES",
    "compute_expire_at",
    "due_templates",
    "generate_for_template",
    "run_generation",
    "trigger_due",
    "trigger_matches_day",
    "utcnow",
]
