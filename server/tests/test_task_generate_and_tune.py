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

from datetime import timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.timeutil import today_bj
from app.dev.seed import SeededFamily, cleanup_family, seed_basic_family
from app.models.enums import ContentMode, TaskStatus, TaskType
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


async def test_tune_task_rejects_explicit_null(
    api_client: AsyncClient, db_session: AsyncSession, seeded: SeededFamily,
):
    """三个字段都是快照,显式 null 一律 422 —— 不静默忽略、也不静默转译成
    "去查模板值"(那会把"一次性填入"伪装成"持续跟随模板")。"""
    from app.services import task_generator_service

    template = await _make_template(db_session, seeded)
    instance, _action = await task_generator_service.generate_for_template(
        db_session, template, manual=True,
    )
    resp = await api_client.patch(
        f"/api/v1/scn/task-instances/{instance.id}",
        json={"xp_reward": None},
        headers=_headers(seeded.parent),
    )
    assert resp.status_code == 422, resp.text


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