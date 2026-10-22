"""任务触发与实例生成器测试(DEV-35 块 A+B)。

覆盖 issue 验收清单:
- 同触发日跑两次 = 1 条实例(幂等);
- 未消费跨天 -> roll_forward 顺延且 generated_for_date 前滚、expire_at 按今日窗口重算;
- 进行中(IN_PROGRESS / PENDING_REVIEW)-> 保持,不新增;
- 已消费(COMPLETED)-> 次日新生;EXPIRED 周期已终结 -> 不顺延,直接新生;
- WEEKDAYS / MONTHLY(含月末钳制)/ CRON / ONCE 命中与不命中;
- 多组触发同日命中 -> 按模板去重只生成 1 条;
- 并发唯一索引兜底 -> 真实 IntegrityError 路径(不 mock 数据库),撞库回捞既有行;
- regenerate -> 终结未消费实例(释放池槽位)并立即建新;
- timed_mode 一致性 / 触发规则字段校验 -> 422;
- 模板库 favorite/apply。

需要可连接的数据库(远程优先),不可达时自动跳过。
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, time, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.timeutil import BJ_TZ
from app.dev.seed import SeededFamily, cleanup_family, seed_basic_family
from app.models.enums import TaskStatus, TimedMode, TriggerKind
from app.models.scn_task_instance import ScnTaskInstance
from app.models.scn_task_template import ScnTaskTemplate
from app.models.scn_task_template_library import ScnTaskTemplateLibrary
from app.models.scn_task_template_trigger import ScnTaskTemplateTrigger
from app.services import auth_service, task_generator_service, task_template_service

pytestmark = pytest.mark.db

TODAY = date(2026, 10, 12)
YESTERDAY = TODAY - timedelta(days=1)
NOW = datetime(2026, 10, 12, 12, 0, tzinfo=BJ_TZ)  # 当日 12:00(北京)


def _cron_dow(day: date) -> int:
    """匹配当日的 cron day_of_week 段。

    校验与匹配统一走 APScheduler CronTrigger,其 day_of_week 语义为
    0=周一..6=周日(与 Python weekday 一致,非 Unix crontab 的 0=周日)。
    """
    return day.weekday()


def _trigger(kind: TriggerKind, **kw) -> ScnTaskTemplateTrigger:
    return ScnTaskTemplateTrigger(kind=kind, generate_at=kw.pop("generate_at", time(0, 0)), **kw)


async def _make_template(
    db: AsyncSession, seeded: SeededFamily, *, triggers: list, **kw,
) -> ScnTaskTemplate:
    template = ScnTaskTemplate(
        family_id=seeded.family.id,
        season_id=seeded.season.id,
        creator_account_id=seeded.parent.id,
        title=kw.pop("title", "生成器测试任务"),
        **kw,
    )
    template.triggers = triggers
    db.add(template)
    await db.commit()
    return template


async def _make_instance(
    db: AsyncSession, template: ScnTaskTemplate, *, day: date | None,
    status: TaskStatus = TaskStatus.AVAILABLE,
) -> ScnTaskInstance:
    expire_at = task_generator_service.compute_expire_at(template, day) if day else None
    instance = ScnTaskInstance(
        family_id=template.family_id,
        season_id=template.season_id,
        template_id=template.id,
        title=template.title,
        xp_reward=template.xp_reward,
        status=status,
        generated_for_date=day,
        expire_at=expire_at,
        time_deposit=template.time_deposit,
    )
    db.add(instance)
    await db.commit()
    return instance


async def _count_instances(db: AsyncSession, template_id: str) -> int:
    rows = (
        await db.execute(
            select(ScnTaskInstance).where(ScnTaskInstance.template_id == template_id)
        )
    ).scalars().all()
    return len(rows)


@pytest_asyncio.fixture
async def seeded(db_session: AsyncSession) -> SeededFamily:
    seeded = await seed_basic_family(db_session, suffix="gen")
    # family.id 提前取普通值:生成器并发兜底的 db.rollback() 会 expire 会话内
    # 全部对象,teardown 时再读 seeded.family.id 会触发隐式重载(MissingGreenlet)。
    family_id = seeded.family.id
    try:
        yield seeded
    finally:
        await cleanup_family(db_session, family_id)


# ---- 1. 同触发日跑两次 = 1 条(幂等) ----


async def test_same_day_double_run_single_instance(db_session, seeded):
    template = await _make_template(
        db_session, seeded, triggers=[_trigger(TriggerKind.DAILY)],
    )
    first, action1 = await task_generator_service.generate_for_template(
        db_session, template, today=TODAY, now=NOW,
    )
    second, action2 = await task_generator_service.generate_for_template(
        db_session, template, today=TODAY, now=NOW,
    )
    assert action1 == "created"
    assert action2 == "exists"
    assert first.id == second.id
    assert await _count_instances(db_session, template.id) == 1
    assert first.generated_for_date == TODAY


# ---- 2. 未消费跨天 -> roll_forward 顺延且日期前滚 ----


async def test_unconsumed_rolls_forward_across_days(db_session, seeded):
    template = await _make_template(
        db_session, seeded,
        triggers=[_trigger(TriggerKind.DAILY)],
        timed_mode=TimedMode.DEADLINE,
        deadline_time=time(20, 0),
    )
    old = await _make_instance(db_session, template, day=YESTERDAY)
    assert old.expire_at is not None and old.expire_at.date() == YESTERDAY

    rolled, action = await task_generator_service.generate_for_template(
        db_session, template, today=TODAY, now=NOW,
    )
    assert action == "rolled_forward"
    assert rolled.id == old.id  # 顺延复用同一行,不新增
    assert rolled.generated_for_date == TODAY  # 日期前滚
    assert rolled.expire_at == datetime(2026, 10, 12, 20, 0, tzinfo=BJ_TZ)  # 按今日窗口重算
    assert await _count_instances(db_session, template.id) == 1


async def test_in_progress_instance_kept_not_duplicated(db_session, seeded):
    template = await _make_template(
        db_session, seeded, triggers=[_trigger(TriggerKind.DAILY)],
    )
    old = await _make_instance(db_session, template, day=YESTERDAY, status=TaskStatus.IN_PROGRESS)
    kept, action = await task_generator_service.generate_for_template(
        db_session, template, today=TODAY, now=NOW,
    )
    assert action == "kept"
    assert kept.id == old.id
    assert kept.generated_for_date == YESTERDAY  # 孩子手里的实例不动
    assert await _count_instances(db_session, template.id) == 1


# ---- 3. 已消费/已过期 -> 次日新生 ----


async def test_completed_generates_new_next_period(db_session, seeded):
    template = await _make_template(
        db_session, seeded, triggers=[_trigger(TriggerKind.DAILY)],
    )
    done = await _make_instance(db_session, template, day=YESTERDAY, status=TaskStatus.COMPLETED)
    fresh, action = await task_generator_service.generate_for_template(
        db_session, template, today=TODAY, now=NOW,
    )
    assert action == "created"
    assert fresh.id != done.id
    assert fresh.generated_for_date == TODAY
    assert await _count_instances(db_session, template.id) == 2


async def test_expired_not_rolled_forward_new_created(db_session, seeded):
    template = await _make_template(
        db_session, seeded, triggers=[_trigger(TriggerKind.DAILY)],
    )
    expired = await _make_instance(db_session, template, day=YESTERDAY, status=TaskStatus.EXPIRED)
    fresh, action = await task_generator_service.generate_for_template(
        db_session, template, today=TODAY, now=NOW,
    )
    assert action == "created"
    assert fresh.id != expired.id  # EXPIRED 不顺延,直接生成新实例
    assert expired.generated_for_date == YESTERDAY
    assert await _count_instances(db_session, template.id) == 2


# ---- 4. WEEKDAYS / MONTHLY / CRON / ONCE 命中 ----


async def test_weekdays_match_and_miss(db_session, seeded):
    hit = await _make_template(
        db_session, seeded,
        triggers=[_trigger(TriggerKind.WEEKDAYS, weekdays=[TODAY.weekday()])],
    )
    miss = await _make_template(
        db_session, seeded,
        triggers=[_trigger(TriggerKind.WEEKDAYS, weekdays=[(TODAY.weekday() + 1) % 7])],
    )
    instance, action = await task_generator_service.generate_for_template(
        db_session, hit, today=TODAY, now=NOW,
    )
    assert action == "created" and instance.generated_for_date == TODAY
    _none, miss_action = await task_generator_service.generate_for_template(
        db_session, miss, today=TODAY, now=NOW,
    )
    assert miss_action == "not_due"
    assert await _count_instances(db_session, miss.id) == 0


def test_monthly_match_and_month_end_clamp():
    """纯函数级:MONTHLY 命中 + 月末不足取当月最后一天。"""
    t = _trigger(TriggerKind.MONTHLY, day_of_month=12)
    assert task_generator_service.trigger_matches_day(t, TODAY) is True
    assert task_generator_service.trigger_matches_day(t, TODAY - timedelta(days=1)) is False

    end_clamp = _trigger(TriggerKind.MONTHLY, day_of_month=31)
    assert task_generator_service.trigger_matches_day(end_clamp, date(2026, 2, 28)) is True  # 2月钳制到28
    assert task_generator_service.trigger_matches_day(end_clamp, date(2026, 2, 27)) is False


def test_cron_match_and_miss():
    """纯函数级:5 段 cron(北京时区)当日命中判断。"""
    dow = _cron_dow(TODAY)
    hit = _trigger(TriggerKind.CRON, cron_expr=f"0 12 * * {dow}")
    miss = _trigger(TriggerKind.CRON, cron_expr=f"0 12 * * {(dow + 1) % 7}")
    assert task_generator_service.trigger_matches_day(hit, TODAY) is True
    assert task_generator_service.trigger_matches_day(miss, TODAY) is False


async def test_once_trigger_only_on_starts_on(db_session, seeded):
    once_today = await _make_template(
        db_session, seeded, triggers=[_trigger(TriggerKind.ONCE, starts_on=TODAY)],
    )
    once_past = await _make_template(
        db_session, seeded, triggers=[_trigger(TriggerKind.ONCE, starts_on=YESTERDAY)],
    )
    instance, action = await task_generator_service.generate_for_template(
        db_session, once_today, today=TODAY, now=NOW,
    )
    assert action == "created" and instance is not None
    _none, past_action = await task_generator_service.generate_for_template(
        db_session, once_past, today=TODAY, now=NOW,
    )
    assert past_action == "not_due"


# ---- 5. 多触发同日去重 ----


async def test_multi_trigger_same_day_dedup(db_session, seeded):
    dow = _cron_dow(TODAY)
    template = await _make_template(
        db_session, seeded,
        triggers=[
            _trigger(TriggerKind.DAILY),
            _trigger(TriggerKind.WEEKDAYS, weekdays=[TODAY.weekday()]),
            _trigger(TriggerKind.CRON, cron_expr=f"0 0 * * {dow}"),
        ],
    )
    _inst, action = await task_generator_service.generate_for_template(
        db_session, template, today=TODAY, now=NOW,
    )
    assert action == "created"
    # 再跑一轮(全量 job 视角),三条规则同日命中仍只有 1 条。
    stats = await task_generator_service.run_generation(db_session, today=TODAY, now=NOW)
    assert stats.get("exists", 0) == 1 and stats.get("created", 0) == 0
    assert await _count_instances(db_session, template.id) == 1


# ---- 6. 并发唯一索引兜底(真实 IntegrityError,不 mock) ----


async def test_concurrent_insert_real_integrity_error_fallback(db_session, seeded):
    """确定性路径:已有同 (template_id, today) 行提交后,再走插入分支,
    数据库真实抛 IntegrityError,由 _insert_instance 回滚回捞既有行。"""
    from app.common.db.engine import AsyncSessionLocal

    template = await _make_template(
        db_session, seeded, triggers=[_trigger(TriggerKind.DAILY)],
    )
    # 会话 A:直接插入并提交当日实例。
    async with AsyncSessionLocal() as session_a:
        winner = await _make_instance(session_a, template, day=TODAY)
    # 会话 B:绕过"先查后插"的业务前置,直接触发插入分支(模拟 A 提交晚于 B 的 SELECT)。
    async with AsyncSessionLocal() as session_b:
        existing = await session_b.execute(
            select(ScnTaskInstance).where(
                ScnTaskInstance.template_id == template.id,
                ScnTaskInstance.generated_for_date == TODAY,
            )
        )
        assert existing.scalar_one_or_none() is not None  # 前置自检:A 行已可见
        # 删除 B 会话对该行的身份映射,保证下面 flush 走 INSERT 而非复用,
        # 从而真实撞上数据库唯一索引。
        session_b.expire_all()
        loser, created = await task_generator_service._insert_instance(
            session_b, template, TODAY, season_id=template.season_id,
        )
        assert created is False  # 兜底回捞,非新建
        assert loser.id == winner.id  # 撞库回捞:A 的行被返回
    assert await _count_instances(db_session, template.id) == 1


async def test_concurrent_generate_for_template_yields_single_row(db_session, seeded):
    """全链路并发:两个独立会话同时对同一模板生成,最终仅 1 条当日实例。"""
    from app.common.db.engine import AsyncSessionLocal

    template = await _make_template(
        db_session, seeded, triggers=[_trigger(TriggerKind.DAILY)],
    )
    # 各自新开会话,保证两边的事务互不可见对方的未提交插入。
    async def _gen() -> tuple:
        async with AsyncSessionLocal() as session:
            # 先物化模板到该会话(expire 避免跨会话复用身份映射)。
            merged = await session.get(ScnTaskTemplate, template.id)
            return await task_generator_service.generate_for_template(
                session, merged, today=TODAY, now=NOW,
            )

    (r1, a1), (r2, a2) = await asyncio.gather(_gen(), _gen())
    assert {a1, a2} <= {"created", "exists", "rolled_forward"}
    assert r1 is not None and r2 is not None
    assert r1.id == r2.id  # 无论谁先插入,另一边都回捞同一行
    assert await _count_instances(db_session, template.id) == 1


# ---- 7. regenerate 终结旧建新 ----


async def test_regenerate_terminalizes_and_creates_fresh(db_session, seeded):
    template = await _make_template(
        db_session, seeded, triggers=[_trigger(TriggerKind.DAILY)],
    )
    old = await _make_instance(db_session, template, day=TODAY)
    tpl_id, terminalized_ids, scheduled_kept, fresh, action = (
        await task_template_service.regenerate_template(
            db_session, family_id=seeded.family.id, template_id=template.id,
        )
    )
    assert tpl_id == template.id
    assert terminalized_ids == [old.id]
    assert scheduled_kept == []  # 没有已排期到未来的实例
    await db_session.refresh(old)
    assert old.status == TaskStatus.EXPIRED
    assert old.generated_for_date is None  # 池槽位已释放
    assert action == "created"
    assert fresh is not None and fresh.id != old.id
    assert fresh.status == TaskStatus.AVAILABLE and fresh.generated_for_date is not None


async def test_regenerate_preserves_pending_review(db_session, seeded):
    """Mars #2(产品拍板):PENDING_REVIEW 不终结,保留审核机会。

    待审核实例仍占实例池槽位(D1),因此本轮不新建:
    - 待审核归属今日 -> action="exists"(同日按日期去重);
    - 待审核归属过去 -> action="kept"(槽位被占,不新增)。
    """
    template = await _make_template(
        db_session, seeded, triggers=[_trigger(TriggerKind.DAILY)],
    )
    available = await _make_instance(db_session, template, day=YESTERDAY - timedelta(days=1))
    reviewing = await _make_instance(
        db_session, template, day=YESTERDAY, status=TaskStatus.PENDING_REVIEW,
    )
    _tpl, terminalized, _scheduled_kept, fresh, action = (
        await task_template_service.regenerate_template(
            db_session, family_id=seeded.family.id, template_id=template.id,
        )
    )
    assert terminalized == [available.id]  # 只终结 AVAILABLE
    await db_session.refresh(reviewing)
    assert reviewing.status == TaskStatus.PENDING_REVIEW  # 待审核不动
    assert reviewing.generated_for_date == YESTERDAY
    assert action == "kept"  # 槽位被待审核占用,不新建
    assert fresh is not None and fresh.id == reviewing.id
    assert await _count_instances(db_session, template.id) == 2

    # 待审核归属"今天"(真实时钟)时为 exists 路径:同样不终结、不新建。
    template2 = await _make_template(
        db_session, seeded, triggers=[_trigger(TriggerKind.DAILY)],
    )
    reviewing_today = await _make_instance(
        db_session, template2, day=TODAY, status=TaskStatus.PENDING_REVIEW,
    )
    _tpl, terminalized2, _sk2, fresh2, action2 = (
        await task_template_service.regenerate_template(
            db_session, family_id=seeded.family.id, template_id=template2.id,
        )
    )
    assert terminalized2 == []
    assert action2 in ("exists", "kept")
    assert fresh2 is not None and fresh2.id == reviewing_today.id
    await db_session.refresh(reviewing_today)
    assert reviewing_today.status == TaskStatus.PENDING_REVIEW


async def test_patch_target_child_id_applies_and_clears(api_client, db_session, seeded):
    """Mars #1(blocker):PATCH target_child_id 必须生效,置 null = 清空指派。"""
    headers = _auth_headers(seeded.parent)
    body = {
        "season_id": seeded.season.id,
        "title": "改派测试",
        "target_child_id": seeded.child.id,
        "triggers": [{"kind": "DAILY", "generate_at": "00:00"}],
    }
    resp = await api_client.post("/api/v1/scn/task-templates", json=body, headers=headers)
    assert resp.status_code == 200, resp.text
    template_id = resp.json()["data"]["id"]
    assert resp.json()["data"]["target_child_id"] == seeded.child.id

    resp = await api_client.patch(
        f"/api/v1/scn/task-templates/{template_id}",
        json={"target_child_id": None}, headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["target_child_id"] is None  # 置 null 清空

    resp = await api_client.patch(
        f"/api/v1/scn/task-templates/{template_id}",
        json={"target_child_id": seeded.child.id}, headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["target_child_id"] == seeded.child.id  # 改回生效


async def test_patch_triggers_after_today_completed(api_client, db_session, seeded):
    """Mars 复核遗留项:孩子当日已完成 → 家长同日 PATCH triggers,强生成撞
    当日已消费行;savepoint 兜底不得 expire 会话对象(否则 MissingGreenlet 500),
    且动作须诚实(exists,而非 created + COMPLETED 冒充新实例)。"""
    headers = _auth_headers(seeded.parent)
    body = {
        "season_id": seeded.season.id,
        "title": "当日完成后改规则",
        "triggers": [{"kind": "DAILY", "generate_at": "00:00"}],
    }
    resp = await api_client.post("/api/v1/scn/task-templates", json=body, headers=headers)
    assert resp.status_code == 200, resp.text
    template_id = resp.json()["data"]["id"]

    # 把当日生成的实例标记为已完成(模拟孩子做完今日任务)。
    today_instance = (
        await db_session.execute(
            select(ScnTaskInstance).where(ScnTaskInstance.template_id == template_id)
        )
    ).scalar_one()
    today_instance.status = TaskStatus.COMPLETED
    await db_session.commit()

    template = await db_session.get(ScnTaskTemplate, template_id)
    _inst, action = await task_generator_service.generate_for_template(
        db_session, template, force=True,
    )
    assert action == "exists"  # 回捞当日已消费行,如实报告
    assert _inst.id == today_instance.id and _inst.status == TaskStatus.COMPLETED

    # API 全链路:PATCH triggers 走同一生成路径,不得 500。
    resp = await api_client.patch(
        f"/api/v1/scn/task-templates/{template_id}",
        json={"triggers": [{"kind": "WEEKDAYS", "weekdays": [0]}]}, headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["triggers"][0]["kind"] == "WEEKDAYS"
    assert await _count_instances(db_session, template_id) == 1  # 未重复生成


async def test_run_generation_survives_today_completed_template(db_session, seeded):
    """Fabio 冒烟 P1-1:库中存在当日已 COMPLETED 实例的模板时,run_generation
    不被生成兜底的 rollback 污染打挂 —— errors==0,后续 due 模板正常生成。"""
    done_tpl = await _make_template(
        db_session, seeded, triggers=[_trigger(TriggerKind.DAILY)],
    )
    await _make_instance(db_session, done_tpl, day=TODAY, status=TaskStatus.COMPLETED)
    fresh_tpl = await _make_template(
        db_session, seeded, triggers=[_trigger(TriggerKind.DAILY)],
    )

    stats = await task_generator_service.run_generation(db_session, today=TODAY, now=NOW)
    assert stats["errors"] == 0
    assert stats["exists"] == 1  # 已消费模板:撞索引回捞,如实 exists
    assert stats["created"] == 1  # 后续 due 模板不受污染,正常生成
    assert await _count_instances(db_session, done_tpl.id) == 1  # 未重复生成
    assert await _count_instances(db_session, fresh_tpl.id) == 1


async def test_delete_refused_with_history(db_session, seeded):
    """Mars #4(产品拍板):存在 COMPLETED/EXPIRED 实例时拒绝硬删(422)。"""
    from app.common.exceptions import ValidationError

    template = await _make_template(
        db_session, seeded, triggers=[_trigger(TriggerKind.DAILY)],
    )
    await _make_instance(db_session, template, day=YESTERDAY, status=TaskStatus.COMPLETED)
    with pytest.raises(ValidationError):
        await task_template_service.delete_template(
            db_session, family_id=seeded.family.id, template_id=template.id,
        )

    # 无历史实例(仅可用态)时硬删成功。
    template2 = await _make_template(
        db_session, seeded, triggers=[_trigger(TriggerKind.DAILY)],
    )
    await _make_instance(db_session, template2, day=TODAY, status=TaskStatus.AVAILABLE)
    await task_template_service.delete_template(
        db_session, family_id=seeded.family.id, template_id=template2.id,
    )
    assert await _count_instances(db_session, template2.id) == 0
    assert await db_session.get(ScnTaskTemplate, template2.id) is None


async def test_generation_skips_already_expired_window(db_session, seeded):
    """nit:生成时刻已过今日截止(生成即过期)时跳过当日生成。"""
    template = await _make_template(
        db_session, seeded,
        triggers=[_trigger(TriggerKind.DAILY)],
        timed_mode=TimedMode.DEADLINE,
        deadline_time=time(0, 5),
    )
    noon = datetime(2026, 10, 12, 12, 0, tzinfo=BJ_TZ)
    _none, action = await task_generator_service.generate_for_template(
        db_session, template, today=TODAY, now=noon,
    )
    assert action == "skipped_expired"
    assert await _count_instances(db_session, template.id) == 0

    early = datetime(2026, 10, 12, 0, 1, tzinfo=BJ_TZ)  # 截止前生成正常
    instance, action = await task_generator_service.generate_for_template(
        db_session, template, today=TODAY, now=early,
    )
    assert action == "created" and instance.expire_at is not None


# ---- 8. timed_mode / 触发规则校验 422(API 层) ----


def _auth_headers(account) -> dict[str, str]:
    tokens = auth_service.issue_token_pair(account)
    return {"Authorization": f"Bearer {tokens.access_token}"}


async def test_api_create_template_and_generate(
    api_client: AsyncClient, db_session, seeded,
):
    headers = _auth_headers(seeded.parent)
    body = {
        "season_id": seeded.season.id,
        "title": "日常阅读",
        "type": "DAILY",
        "triggers": [{"kind": "DAILY", "generate_at": "00:00"}],
    }
    resp = await api_client.post("/api/v1/scn/task-templates", json=body, headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["timed_mode"] == "NONE"
    assert data["pool_policy"] == "REUSE_UNTIL_CONSUMED"
    assert [t["kind"] for t in data["triggers"]] == ["DAILY"]
    # 创建后立即生成:当日实例已物化(即使 generate_at 时刻由 force 跳过)。
    rows = (
        await db_session.execute(
            select(ScnTaskInstance).where(ScnTaskInstance.template_id == data["id"])
        )
    ).scalars().all()
    assert len(rows) == 1 and rows[0].generated_for_date is not None


async def test_api_timed_mode_validation_422(api_client: AsyncClient, seeded):
    headers = _auth_headers(seeded.parent)
    base = {"season_id": seeded.season.id, "title": "限时任务"}

    # DEADLINE 缺 deadline_time -> 422
    resp = await api_client.post(
        "/api/v1/scn/task-templates",
        json={**base, "timed_mode": "DEADLINE"}, headers=headers,
    )
    assert resp.status_code == 422
    # DURATION 缺 duration_minutes -> 422
    resp = await api_client.post(
        "/api/v1/scn/task-templates",
        json={**base, "timed_mode": "DURATION", "start_time": "09:00"}, headers=headers,
    )
    assert resp.status_code == 422
    # NONE 带了 deadline_time -> 422
    resp = await api_client.post(
        "/api/v1/scn/task-templates",
        json={**base, "timed_mode": "NONE", "deadline_time": "20:00"}, headers=headers,
    )
    assert resp.status_code == 422


async def test_api_trigger_validation_422(api_client: AsyncClient, seeded):
    headers = _auth_headers(seeded.parent)
    base = {"season_id": seeded.season.id, "title": "触发规则校验"}

    # WEEKDAYS 缺 weekdays -> 422
    resp = await api_client.post(
        "/api/v1/scn/task-templates",
        json={**base, "triggers": [{"kind": "WEEKDAYS"}]}, headers=headers,
    )
    assert resp.status_code == 422
    # CRON 表达式不是 5 段 -> 422
    resp = await api_client.post(
        "/api/v1/scn/task-templates",
        json={**base, "triggers": [{"kind": "CRON", "cron_expr": "not-a-cron"}]}, headers=headers,
    )
    assert resp.status_code == 422
    # ONCE 缺 starts_on -> 422
    resp = await api_client.post(
        "/api/v1/scn/task-templates",
        json={**base, "triggers": [{"kind": "ONCE"}]}, headers=headers,
    )
    assert resp.status_code == 422


# ---- 9. 模板库 favorite / apply ----


async def test_library_favorite_and_apply(db_session, seeded):
    entry = ScnTaskTemplateLibrary(
        family_id=None,  # 系统预置
        title="每天练琴 30 分钟",
        description="音乐素养",
        suggested_xp=80,
        suggested_time_deposit=15,
        meta={},
    )
    db_session.add(entry)
    await db_session.commit()

    rows, favorites = await task_template_service.list_library(
        db_session, family_id=seeded.family.id,
    )
    assert entry.id in {r.id for r in rows} and entry.id not in favorites

    assert await task_template_service.toggle_favorite(
        db_session, family_id=seeded.family.id, entry_id=entry.id,
    ) is True
    _rows, favorites = await task_template_service.list_library(
        db_session, family_id=seeded.family.id,
    )
    assert entry.id in favorites

    template = await task_template_service.apply_library_entry(
        db_session, family_id=seeded.family.id, creator_id=seeded.parent.id,
        entry_id=entry.id, season_id=seeded.season.id, target_child_id=seeded.child.id,
    )
    assert template.library_id == entry.id
    assert template.xp_reward == 80 and template.time_deposit == 15
    assert [t.kind for t in template.triggers] == [TriggerKind.DAILY]  # DAILY 默认规则

    assert await task_template_service.toggle_favorite(
        db_session, family_id=seeded.family.id, entry_id=entry.id,
    ) is False  # 再切一次 = 取消收藏
