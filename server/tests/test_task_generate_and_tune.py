"""DEV-50:选模板生成 / 逐实例微调 / 可见性与实例池口径。

覆盖已冻结契约里最容易做错的几条:

- 生成:`target_date` 默认今天、`< 今天` 与 `> +30 天` 均 422(一律 `today_bj()`);
  豁免触发规则;赛季取**生成当时的激活赛季**,无激活赛季 409;
  幂等返回 `created / exists / rolled_forward / kept / skipped_expired`。
- 池口径:`generated_for_date IS NULL OR <= today` 才算池 —— **未来实例不入池、
  不占槽、不被顺延**,所以"为明天预生成"不会被今天的在途任务挡住。
- 快照:`difficulty / time_deposit / xp_reward` 生成即定值,**改模板不影响已生成
  的未结算实例**(docs/15 §12 P2);三者显式 `null` 一律 422。
- 可见性:孩子端由服务端强制过滤(含 `generated_for_date IS NULL` 的存量行),
  管理端看全量;`start` 对"已排期到未来"的实例返回 409。

需要可连接的数据库(远程优先),不可达时本模块用例被 `db_ready` 跳过。
"""
from __future__ import annotations

from datetime import time, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.timeutil import today_bj
from app.dev.seed import SeededFamily, cleanup_family, seed_basic_family
from app.models.enums import ContentMode, TaskStatus, TaskType, TimedMode
from app.models.scn_task_instance import ScnTaskInstance
from app.models.scn_task_template import ScnTaskTemplate
from app.services import auth_service

pytestmark = pytest.mark.db


def _headers(account) -> dict[str, str]:
    tokens = auth_service.issue_token_pair(account)
    return {"Authorization": f"Bearer {tokens.access_token}"}


async def _make_template(
    db: AsyncSession, seeded: SeededFamily, **kw,
) -> ScnTaskTemplate:
    """直接落库建模板(不走 API):避免 `create_template` 的"创建即补生成一条
    当天实例"把下面的池/幂等断言搅浑。"""
    template = ScnTaskTemplate(
        family_id=seeded.family.id,
        season_id=seeded.season.id,
        creator_account_id=seeded.parent.id,
        title=kw.pop("title", "DEV-50 生成测试"),
        type=kw.pop("type", TaskType.DAILY),
        difficulty=kw.pop("difficulty", 2),
        # 缺省走 STATIC:本文件测的是生成/微调契约,不该真的去调 LLM
        # (默认已翻转为 LLM,不显式指定会发起真实网络调用)。
        content_mode=kw.pop("content_mode", ContentMode.STATIC),
        **kw,
    )
    db.add(template)
    await db.commit()
    return template


@pytest_asyncio.fixture
async def seeded(db_session: AsyncSession) -> SeededFamily:
    seeded = await seed_basic_family(db_session, suffix="dev50")
    family_id = seeded.family.id  # 生成兜底的 rollback 会 expire 对象,先取普通值
    try:
        yield seeded
    finally:
        await cleanup_family(db_session, family_id)


# ---- 1. 生成:今天 + 覆盖值 ----


async def test_generate_today_applies_overrides(
    api_client: AsyncClient, db_session: AsyncSession, seeded: SeededFamily,
):
    template = await _make_template(db_session, seeded, xp_reward=50, time_deposit=10)
    resp = await api_client.post(
        f"/api/v1/scn/task-templates/{template.id}/generate",
        json={"difficulty": 4, "time_deposit": 7, "xp_reward": 88},
        headers=_headers(seeded.parent),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["action"] == "created"
    assert data["overrides_applied"] is True
    assert data["generated_for_date"] == str(today_bj())
    assert data["difficulty"] == 4
    assert data["time_deposit"] == 7  # 显式值经类型区间 clamp(DAILY 5-20)后仍为 7
    assert data["xp_reward"] == 88
    assert data["season_name"] == seeded.season.name  # 赛季取生成时的激活赛季


async def test_generate_without_overrides_snapshots_template(
    api_client: AsyncClient, db_session: AsyncSession, seeded: SeededFamily,
):
    """未传 = 用模板值(快照),不是"不落值"。"""
    template = await _make_template(
        db_session, seeded, xp_reward=66, time_deposit=12, difficulty=3,
    )
    resp = await api_client.post(
        f"/api/v1/scn/task-templates/{template.id}/generate",
        json={}, headers=_headers(seeded.parent),
    )
    data = resp.json()["data"]
    assert data["action"] == "created"
    assert (data["difficulty"], data["time_deposit"], data["xp_reward"]) == (3, 12, 66)


# ---- 2. 日期校验 ----


async def test_generate_rejects_past_and_too_far_dates(
    api_client: AsyncClient, db_session: AsyncSession, seeded: SeededFamily,
):
    template = await _make_template(db_session, seeded)
    headers = _headers(seeded.parent)
    path = f"/api/v1/scn/task-templates/{template.id}/generate"

    past = await api_client.post(
        path, json={"target_date": str(today_bj() - timedelta(days=1))}, headers=headers,
    )
    assert past.status_code == 422, past.text
    assert "不能早于今天" in past.text

    far = await api_client.post(
        path, json={"target_date": str(today_bj() + timedelta(days=31))}, headers=headers,
    )
    assert far.status_code == 422, far.text
    assert "最多提前" in far.text


async def test_generate_defaults_to_today_and_accepts_boundary(
    api_client: AsyncClient, db_session: AsyncSession, seeded: SeededFamily,
):
    template = await _make_template(db_session, seeded)
    headers = _headers(seeded.parent)
    path = f"/api/v1/scn/task-templates/{template.id}/generate"

    # 上界恰好 +30 天应当被接受。
    edge = await api_client.post(
        path, json={"target_date": str(today_bj() + timedelta(days=30))}, headers=headers,
    )
    assert edge.status_code == 200, edge.text
    assert edge.json()["data"]["generated_for_date"] == str(today_bj() + timedelta(days=30))


# ---- 3. 未来实例不入池、幂等 ----


async def test_future_instance_not_in_pool_and_idempotent(
    api_client: AsyncClient, db_session: AsyncSession, seeded: SeededFamily,
):
    """未来实例不入池、不占槽:为明天预生成后,今天照样能生成(互不影响);
    同一未来日期重复生成 → exists 且不覆盖。"""
    template = await _make_template(db_session, seeded, difficulty=2)
    headers = _headers(seeded.parent)
    path = f"/api/v1/scn/task-templates/{template.id}/generate"
    tomorrow = today_bj() + timedelta(days=1)

    first = await api_client.post(
        path, json={"target_date": str(tomorrow), "difficulty": 5}, headers=headers,
    )
    assert first.json()["data"]["action"] == "created"
    assert first.json()["data"]["generated_for_date"] == str(tomorrow)

    # 今天仍可生成:未来实例没有占掉池槽位。
    today_resp = await api_client.post(path, json={}, headers=headers)
    assert today_resp.json()["data"]["action"] == "created"
    assert today_resp.json()["data"]["generated_for_date"] == str(today_bj())

    # 同一未来日期再来一次:幂等复用,且**不写入**覆盖值。
    again = await api_client.post(
        path, json={"target_date": str(tomorrow), "difficulty": 1}, headers=headers,
    )
    data = again.json()["data"]
    assert data["action"] == "exists"
    assert data["overrides_applied"] is False
    assert data["difficulty"] == 5  # 既有实例的覆盖值未被改写

    rows = (
        await db_session.execute(
            select(ScnTaskInstance).where(ScnTaskInstance.template_id == template.id)
        )
    ).scalars().all()
    assert sorted(r.generated_for_date for r in rows) == sorted([today_bj(), tomorrow])


async def test_future_instance_not_rolled_forward_by_daily_job(
    api_client: AsyncClient, db_session: AsyncSession, seeded: SeededFamily,
):
    """夜间作业不得把"已排期到明天"的实例拉回今天。"""
    from app.services import task_generator_service

    template = await _make_template(db_session, seeded)
    tomorrow = today_bj() + timedelta(days=1)
    await task_generator_service.manual_generate(db_session, template, target_date=tomorrow)

    _instance, action = await task_generator_service.generate_for_template(
        db_session, template, manual=True,
    )
    # 目标日 == 今天;池内没有实例(未来那条不入池),因此应新建而不是顺延未来那条。
    assert action == "created"

    rows = (
        await db_session.execute(
            select(ScnTaskInstance).where(ScnTaskInstance.template_id == template.id)
        )
    ).scalars().all()
    future_row = next(r for r in rows if r.generated_for_date == tomorrow)
    assert future_row.generated_for_date == tomorrow  # 日期未被改写


# ---- 4. 无激活赛季 ----


async def test_generate_without_active_season_conflicts(
    api_client: AsyncClient, db_session: AsyncSession, seeded: SeededFamily,
):
    template = await _make_template(db_session, seeded)
    seeded.season.is_active = False
    await db_session.commit()

    resp = await api_client.post(
        f"/api/v1/scn/task-templates/{template.id}/generate",
        json={}, headers=_headers(seeded.parent),
    )
    assert resp.status_code == 409, resp.text
    assert "赛季" in resp.text


# ---- 5. 微调 ----


async def test_tune_task_sets_snapshot_fields(
    api_client: AsyncClient, db_session: AsyncSession, seeded: SeededFamily,
):
    from app.services import task_generator_service

    template = await _make_template(db_session, seeded, difficulty=2, xp_reward=50, time_deposit=10)
    instance, _action = await task_generator_service.generate_for_template(
        db_session, template, manual=True,
    )

    resp = await api_client.patch(
        f"/api/v1/scn/task-instances/{instance.id}",
        json={"difficulty": 5, "time_deposit": 15, "xp_reward": 90},
        headers=_headers(seeded.parent),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert (data["difficulty"], data["time_deposit"], data["xp_reward"]) == (5, 15, 90)


@pytest.mark.parametrize("field", ["difficulty", "time_deposit", "xp_reward"])
async def test_tune_task_rejects_explicit_null(
    api_client: AsyncClient, db_session: AsyncSession, seeded: SeededFamily, field: str,
):
    """三个字段**都**是快照,显式 null 一律 422 —— 不静默忽略、也不静默转译成
    "去查模板值"(那会把"一次性填入"伪装成"持续跟随模板")。三字段逐个覆盖。"""
    from app.services import task_generator_service

    template = await _make_template(db_session, seeded)
    instance, _action = await task_generator_service.generate_for_template(
        db_session, template, manual=True,
    )
    resp = await api_client.patch(
        f"/api/v1/scn/task-instances/{instance.id}",
        json={field: None},
        headers=_headers(seeded.parent),
    )
    assert resp.status_code == 422, resp.text
    assert field in resp.text


async def test_tune_task_rejected_after_start(
    api_client: AsyncClient, db_session: AsyncSession, seeded: SeededFamily,
):
    """接取后押金已扣,再改会让结算口径漂移 —— 仅未接取可调。"""
    from app.services import task_generator_service

    template = await _make_template(db_session, seeded, time_deposit=5, xp_reward=50)
    instance, _action = await task_generator_service.generate_for_template(
        db_session, template, manual=True,
    )
    instance.status = TaskStatus.IN_PROGRESS
    await db_session.commit()

    resp = await api_client.patch(
        f"/api/v1/scn/task-instances/{instance.id}",
        json={"difficulty": 3},
        headers=_headers(seeded.parent),
    )
    assert resp.status_code == 409, resp.text


# ---- 6. 难度快照:改模板不影响已生成实例 ----


async def test_difficulty_is_snapshot_not_template_reference(
    api_client: AsyncClient, db_session: AsyncSession, seeded: SeededFamily,
):
    """docs/15 §12 P2:生成即定值 —— 之后改模板难度**不会**移动已生成实例。

    这是"快照"与"读时回落模板"的分水岭:后者会让改模板追溯影响未结算实例的 XP。
    """
    from app.services import task_generator_service

    template = await _make_template(db_session, seeded, difficulty=5)
    instance, _action = await task_generator_service.generate_for_template(
        db_session, template, manual=True,
    )
    assert instance.difficulty == 5

    template.difficulty = 1
    await db_session.commit()

    row = (
        await db_session.execute(
            select(ScnTaskInstance)
            .where(ScnTaskInstance.id == instance.id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    assert row.difficulty == 5, "实例难度是快照,不应跟随模板变化"


# ---- 7. 可见性:孩子端强制过滤,管理端全量 ----


async def test_visibility_child_filtered_parent_full(
    api_client: AsyncClient, db_session: AsyncSession, seeded: SeededFamily,
):
    from app.services import task_generator_service

    template = await _make_template(db_session, seeded)
    future, _action, _applied = await task_generator_service.manual_generate(
        db_session, template, target_date=today_bj() + timedelta(days=2),
    )
    # 存量一次性任务:旧 POST /scn/tasks 路径写 NULL,必须仍对孩子可见。
    legacy = ScnTaskInstance(
        family_id=seeded.family.id,
        season_id=seeded.season.id,
        template_id=template.id,
        title="存量一次性任务",
        xp_reward=50,
        status=TaskStatus.AVAILABLE,
        generated_for_date=None,
        time_deposit=10,
    )
    db_session.add(legacy)
    await db_session.commit()

    child_ids = await _list_ids(api_client, seeded.child_account)
    assert future.id not in child_ids, "未来实例不该出现在孩子端"
    assert legacy.id in child_ids, "generated_for_date IS NULL 的存量任务必须保留"

    parent_ids = await _list_ids(api_client, seeded.parent)
    assert future.id in parent_ids, "管理端看全量(家长要能看见自己排期的任务)"


async def _list_ids(api_client: AsyncClient, account) -> set[str]:
    resp = await api_client.get(
        "/api/v1/scn/task-instances", params={"page_size": 200}, headers=_headers(account),
    )
    assert resp.status_code == 200, resp.text
    return {item["id"] for item in resp.json()["data"]["items"]}


# ---- 8. 接取守卫 ----


async def test_child_cannot_start_scheduled_future_instance(
    api_client: AsyncClient, db_session: AsyncSession, seeded: SeededFamily,
):
    """列表过滤只解决"看不见";拿到 id 也不能接走"已排期到明天"的任务。"""
    from app.services import task_generator_service

    template = await _make_template(db_session, seeded, time_deposit=5)
    instance, _action, _applied = await task_generator_service.manual_generate(
        db_session, template, target_date=today_bj() + timedelta(days=1),
    )
    resp = await api_client.post(
        f"/api/v1/scn/task-instances/{instance.id}/start",
        headers=_headers(seeded.child_account),
    )
    assert resp.status_code == 409, resp.text
    assert "已排期" in resp.text


# ---- 9. 模板列表:season_name ----


# ---- 10. 审查 🟡4:链式第 2..N 步不可手动生成 ----


async def test_generate_rejected_for_chain_step_after_first(
    api_client: AsyncClient, db_session: AsyncSession, seeded: SeededFamily,
):
    """链式第 2..N 步模板没有触发规则,自动路径不碰,但手动路径会绕开逐步解锁:

    - 今天生成:会把 `generated_for_date IS NULL` 的链式实例捞进池、盖上今天
      的日期,使它此后受"仅当天可接取"约束;
    - 未来日期:直接建平行实例,绕过"上一步完成才解锁下一步"。
    投放链步只由 `chain_service.spawn_next_chain_step` 负责 → 409。
    """
    step2 = await _make_template(
        db_session, seeded, title="链第二步", type=TaskType.CHAIN,
        chain_key="fix-chain", chain_order=2, chain_total=3,
    )
    resp = await api_client.post(
        f"/api/v1/scn/task-templates/{step2.id}/generate",
        json={}, headers=_headers(seeded.parent),
    )
    assert resp.status_code == 409, resp.text
    assert "链" in resp.text

    # 链首(order=1)不受影响。
    step1 = await _make_template(
        db_session, seeded, title="链首", type=TaskType.CHAIN,
        chain_key="fix-chain-2", chain_order=1, chain_total=2,
    )
    ok_resp = await api_client.post(
        f"/api/v1/scn/task-templates/{step1.id}/generate",
        json={}, headers=_headers(seeded.parent),
    )
    assert ok_resp.status_code == 200, ok_resp.text


# ---- 11. 审查 🟡3:详情接口对孩子端同一条可见性边界 ----


async def test_child_cannot_read_scheduled_future_instance_detail(
    api_client: AsyncClient, db_session: AsyncSession, seeded: SeededFamily,
):
    """列表那半边是按权限边界做的(服务端强制),详情必须同口径;否则"看不见"
    只做了一半。孩子读到未来实例 → 404(不泄露它存在,与跨家庭口径一致)。"""
    from app.services import task_generator_service

    template = await _make_template(db_session, seeded)
    future, _a, _p = await task_generator_service.manual_generate(
        db_session, template, target_date=today_bj() + timedelta(days=1),
    )
    path = f"/api/v1/scn/task-instances/{future.id}"

    child = await api_client.get(path, headers=_headers(seeded.child_account))
    assert child.status_code == 404, child.text

    parent = await api_client.get(path, headers=_headers(seeded.parent))
    assert parent.status_code == 200, parent.text

    # 今天及以前的实例对孩子照常可见。
    inst_today, _a, _p = await task_generator_service.manual_generate(
        db_session, template, target_date=today_bj(),
    )
    ok_child = await api_client.get(
        f"/api/v1/scn/task-instances/{inst_today.id}", headers=_headers(seeded.child_account),
    )
    assert ok_child.status_code == 200, ok_child.text


# ---- 12. 审查 🟡5:regenerate 不终结"已排期到未来"的实例 ----


async def test_regenerate_skips_scheduled_future_instances(
    api_client: AsyncClient, db_session: AsyncSession, seeded: SeededFamily,
):
    """预排期引入后,池能同时装下当天 + 多条未来实例;一次确认不该把明天排好的
    任务一起清掉。终结范围收窄为 `IS NULL OR <= today`,并回报未终结的条数供
    前端点名。"""
    from app.services import task_generator_service

    template = await _make_template(db_session, seeded, time_deposit=5)
    today_inst, _a, _p = await task_generator_service.manual_generate(
        db_session, template, target_date=today_bj(),
    )
    future_inst, _a, _p = await task_generator_service.manual_generate(
        db_session, template, target_date=today_bj() + timedelta(days=2),
    )

    resp = await api_client.post(
        f"/api/v1/scn/task-templates/{template.id}/regenerate",
        json={}, headers=_headers(seeded.parent),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert today_inst.id in data["terminalized_instance_ids"]
    assert future_inst.id not in data["terminalized_instance_ids"]
    assert data["scheduled_kept_instance_ids"] == [future_inst.id]
    assert data["scheduled_kept_count"] == 1

    row = (
        await db_session.execute(
            select(ScnTaskInstance)
            .where(ScnTaskInstance.id == future_inst.id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    assert row.status == TaskStatus.AVAILABLE  # 未被终结
    assert row.generated_for_date == today_bj() + timedelta(days=2)  # 日期未被改写


# ---- 13. 审查顺手项:extra="forbid" ----


async def test_requests_reject_unknown_fields(
    api_client: AsyncClient, db_session: AsyncSession, seeded: SeededFamily,
):
    """多余字段一律 422,不静默忽略 —— 否则客户端把 `season_id` 塞进 PATCH
    会以为"改成功了"(实例赛季本来不可改)。"""
    from app.services import task_generator_service

    template = await _make_template(db_session, seeded)
    instance, _action = await task_generator_service.generate_for_template(
        db_session, template, manual=True,
    )
    patch = await api_client.patch(
        f"/api/v1/scn/task-instances/{instance.id}",
        json={"difficulty": 3, "season_id": seeded.season.id},
        headers=_headers(seeded.parent),
    )
    assert patch.status_code == 422, patch.text

    gen = await api_client.post(
        f"/api/v1/scn/task-templates/{template.id}/generate",
        json={"chain_order": 99}, headers=_headers(seeded.parent),
    )
    assert gen.status_code == 422, gen.text


# ---- 14. 审查顺手项:微调押金封顶取实例的目标日 ----


async def test_tune_deposit_cap_uses_instance_target_day(
    api_client: AsyncClient, db_session: AsyncSession, seeded: SeededFamily,
):
    """配额按星期几不同,封顶必须按**实例的目标日**算 —— 拿今天的配额去卡一条
    排期在低配额日的实例会算错。"""
    from app.models.scn_time_config_exception import ScnTimeConfigException
    from app.services import coin_service, task_generator_service

    target = today_bj() + timedelta(days=1)
    # 该表口径 0=周日..6=周六;Python weekday() 是 0=周一..6=周日。
    target_dow_table = (target.weekday() + 1) % 7
    # 本家庭的 time_config 可能已被前面的押金解析建出来了 —— 取而不是新建,
    # 否则撞 ix_scn_time_config_family_id 唯一索引。
    cfg = await coin_service.get_or_create_time_config(db_session, seeded.family.id)
    db_session.add(ScnTimeConfigException(
        time_config_id=cfg.id, day_of_week=target_dow_table, coin_amount=10,
    ))
    await db_session.commit()

    template = await _make_template(db_session, seeded, time_deposit=10)
    instance, _a, _p = await task_generator_service.manual_generate(
        db_session, template, target_date=target,
    )

    # DAILY 区间 [5,20];目标日配额 10 → 封顶 floor(10*0.5)=5。
    resp = await api_client.patch(
        f"/api/v1/scn/task-instances/{instance.id}",
        json={"time_deposit": 20}, headers=_headers(seeded.parent),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["time_deposit"] == 5

    # 反证:同样 20 押金、但实例归属今天(配额 100 → 封顶 50)时不被压到 5。
    today_inst, _a, _p = await task_generator_service.manual_generate(
        db_session, template, target_date=today_bj(),
    )
    resp_today = await api_client.patch(
        f"/api/v1/scn/task-instances/{today_inst.id}",
        json={"time_deposit": 20}, headers=_headers(seeded.parent),
    )
    assert resp_today.status_code == 200, resp_today.text
    assert resp_today.json()["data"]["time_deposit"] == 20


async def test_generate_skipped_expired_returns_all_null_fields(
    api_client: AsyncClient, db_session: AsyncSession, seeded: SeededFamily,
):
    """限时模板当天截止时刻已过 → 不产出实例。该分支的 7 个字段全为 null
    (审查 🟡2 的运行时事实,前端据此单独出文案,不能套绿色成功框)。"""
    template = await _make_template(
        db_session, seeded,
        timed_mode=TimedMode.DEADLINE, deadline_time=time(0, 1),
    )
    resp = await api_client.post(
        f"/api/v1/scn/task-templates/{template.id}/generate",
        json={}, headers=_headers(seeded.parent),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["action"] == "skipped_expired"
    for key in (
        "instance_id", "generated_for_date", "status", "difficulty",
        "time_deposit", "xp_reward", "content_source", "season_name",
    ):
        assert data[key] is None, f"{key} 应为 null"
    assert data["overrides_applied"] is False


def test_template_default_content_mode_flipped_to_llm():
    """DEV-50:新模板默认 LLM —— 业主口径"生成任务时要调 LLM 结合赛季背景"的直接推论。

    只比对默认值(真生成一次会发起真实 LLM 调用,不适合放进测试)。
    注意 DB 层 `server_default` 仍是 `STATIC`(docs/15 R1 的存量回填口径),
    翻转发生在**应用层**:凡是经 ORM 建的模板都取 LLM。裸 SQL 插入(仅测试/
    脚本会用)仍拿到 STATIC。
    """
    from app.schemas.task import TaskTemplateCreate

    body = TaskTemplateCreate.model_validate({"title": "默认值探测"})
    assert body.content_mode == ContentMode.LLM
    assert ScnTaskTemplate.__table__.c.content_mode.default.arg == ContentMode.LLM


async def test_template_list_exposes_source_season_name(
    api_client: AsyncClient, db_session: AsyncSession, seeded: SeededFamily,
):
    await _make_template(db_session, seeded)
    resp = await api_client.get(
        "/api/v1/scn/task-templates", headers=_headers(seeded.parent),
    )
    assert resp.status_code == 200, resp.text
    rows = resp.json()["data"]
    assert any(r["season_name"] == seeded.season.name for r in rows)