"""DEV-59:临时任务(只建实例、不落模板)。

覆盖已冻结契约里最容易做错的几条:

- **不落模板**:`POST /scn/task-instances` 带 `ephemeral=true` 后,
  `scn_task_template` 不新增行;实例 `template_id IS NULL`(读取端的空值语义)。
- **`generated_for_date` 生效**:临时任务写逻辑日 → 自动继承既有的
  「未来实例不可见 / 不可接取」边界;同一天可建多条(NULL 不撞唯一索引)。
- **模板级字段一律 422**(triggers/library_id/type≠DAILY/timed_mode/链式):
  临时任务没有模板行,配了也无处安放,静默丢弃会让家长以为"配了却没生效"。
- **结算路径不受影响**:无模板实例照样可被孩子接取(扣押金),`_deposit_of`
  只读实例自身列。

需要可连接的数据库(远程优先),不可达时本模块用例被 `db_ready` 跳过。
"""
from __future__ import annotations

from datetime import timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.timeutil import today_bj
from app.dev.seed import SeededFamily, cleanup_family, seed_basic_family
from app.models.enums import ContentSource, TaskStatus
from app.models.scn_task_instance import ScnTaskInstance
from app.models.scn_task_template import ScnTaskTemplate
from app.services import auth_service

pytestmark = pytest.mark.db

PATH = "/api/v1/scn/task-instances"


def _headers(account) -> dict[str, str]:
    tokens = auth_service.issue_token_pair(account)
    return {"Authorization": f"Bearer {tokens.access_token}"}


@pytest_asyncio.fixture
async def seeded(db_session: AsyncSession) -> SeededFamily:
    seeded = await seed_basic_family(db_session, suffix="dev59")
    family_id = seeded.family.id
    try:
        yield seeded
    finally:
        await cleanup_family(db_session, family_id)


async def _template_count(db: AsyncSession, family_id: str) -> int:
    return int(
        (
            await db.execute(
                select(func.count())
                .select_from(ScnTaskTemplate)
                .where(ScnTaskTemplate.family_id == family_id)
            )
        ).scalar_one()
    )


def _body(seeded: SeededFamily, **over) -> dict:
    payload = {
        "ephemeral": True,
        "title": "临时任务:收拾书桌",
        "description": "把书桌清空并擦一遍",
        "xp_reward": 40,
        "season_id": seeded.season.id,
    }
    payload.update(over)
    return payload


# ---- 1. 只建实例、不落模板 ----


async def test_ephemeral_create_adds_no_template_row(
    api_client: AsyncClient, db_session: AsyncSession, seeded: SeededFamily,
):
    before = await _template_count(db_session, seeded.family.id)

    resp = await api_client.post(PATH, json=_body(seeded, difficulty=4), headers=_headers(seeded.parent))
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]

    # 返回体 template_id 语义:临时任务恒为 null(不由模板生成)。
    assert data["template_id"] is None
    assert data["generated_for_date"] == str(today_bj())
    assert data["title"] == "临时任务:收拾书桌"
    assert data["difficulty"] == 4
    assert data["season_id"] == seeded.season.id

    # 模板库不留痕 —— 这是业主裁决的核心。
    assert await _template_count(db_session, seeded.family.id) == before, "临时任务不得新增模板行"

    row = (
        await db_session.execute(
            select(ScnTaskInstance).where(ScnTaskInstance.id == data["id"])
        )
    ).scalar_one()
    assert row.template_id is None
    assert row.status == TaskStatus.AVAILABLE
    assert row.description == "把书桌清空并擦一遍"
    assert row.xp_reward == 40
    assert row.content_source == ContentSource.TEMPLATE  # 不经生成器


async def test_ephemeral_explicit_deposit_is_stored(
    api_client: AsyncClient, db_session: AsyncSession, seeded: SeededFamily,
):
    """显式押金照常落库(过 resolve_deposit 的 clamp);缺省则由后端解析。"""
    resp = await api_client.post(
        PATH, json=_body(seeded, time_deposit=8), headers=_headers(seeded.parent),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["time_deposit"] == 8

    defaulted = await api_client.post(PATH, json=_body(seeded), headers=_headers(seeded.parent))
    assert defaulted.status_code == 200, defaulted.text
    assert defaulted.json()["data"]["time_deposit"] > 0, "缺省也应有解析后的押金,不是 0"


# ---- 2. 逻辑日 / 未来实例边界 ----


async def test_ephemeral_future_date_is_scheduled_and_same_day_multi_allowed(
    api_client: AsyncClient, db_session: AsyncSession, seeded: SeededFamily,
):
    """写入 generated_for_date 后沿用既有可见性边界;NULL template_id 不撞同日唯一索引。"""
    tomorrow = today_bj() + timedelta(days=1)
    future = await api_client.post(
        PATH, json=_body(seeded, target_date=str(tomorrow)), headers=_headers(seeded.parent),
    )
    assert future.status_code == 200, future.text
    assert future.json()["data"]["generated_for_date"] == str(tomorrow)

    # 未来临时任务:孩子端不可见、不可接取(与模板实例同一条边界)。
    child_ids = await _list_ids(api_client, seeded.child_account)
    assert future.json()["data"]["id"] not in child_ids
    start = await api_client.post(
        f"{PATH}/{future.json()['data']['id']}/start", headers=_headers(seeded.child_account),
    )
    assert start.status_code == 409, start.text

    # 同一天多条临时任务:template_id IS NULL 在 Postgres 唯一索引里互不相同。
    first = await api_client.post(PATH, json=_body(seeded), headers=_headers(seeded.parent))
    second = await api_client.post(PATH, json=_body(seeded), headers=_headers(seeded.parent))
    assert first.status_code == 200 and second.status_code == 200, (first.text, second.text)
    assert first.json()["data"]["id"] != second.json()["data"]["id"]


async def test_ephemeral_rejects_past_and_too_far_dates(
    api_client: AsyncClient, db_session: AsyncSession, seeded: SeededFamily,
):
    headers = _headers(seeded.parent)
    past = await api_client.post(
        PATH, json=_body(seeded, target_date=str(today_bj() - timedelta(days=1))), headers=headers,
    )
    assert past.status_code == 422, past.text
    assert "不能早于今天" in past.text

    far = await api_client.post(
        PATH, json=_body(seeded, target_date=str(today_bj() + timedelta(days=31))), headers=headers,
    )
    assert far.status_code == 422, far.text
    assert "最多提前" in far.text


# ---- 3. 模板级字段:显式 422,不静默丢弃 ----


@pytest.mark.parametrize(
    "over, expected",
    [
        ({"triggers": [{"kind": "DAILY"}]}, "触发规则"),
        ({"library_id": "00000000-0000-0000-0000-000000000000"}, "模板库"),
        ({"type": "CHALLENGE"}, "type=DAILY"),
        ({"timed_mode": "DEADLINE", "deadline_time": "20:00"}, "时间窗"),
        ({"chain_key": "c1", "chain_order": 1, "chain_total": 2}, "链式"),
    ],
)
async def test_ephemeral_rejects_template_scoped_fields(
    api_client: AsyncClient, db_session: AsyncSession, seeded: SeededFamily,
    over: dict, expected: str,
):
    resp = await api_client.post(PATH, json=_body(seeded, **over), headers=_headers(seeded.parent))
    assert resp.status_code == 422, resp.text
    assert expected in resp.text


async def test_non_ephemeral_rejects_target_date(
    api_client: AsyncClient, db_session: AsyncSession, seeded: SeededFamily,
):
    """target_date 只对临时任务有意义;旧(deprecated)路径传了不生效 → 422。"""
    resp = await api_client.post(
        PATH,
        json={"title": "旧路径", "season_id": seeded.season.id, "target_date": str(today_bj())},
        headers=_headers(seeded.parent),
    )
    assert resp.status_code == 422, resp.text
    assert "target_date" in resp.text


# ---- 4. 无激活赛季 ----


async def test_ephemeral_without_active_season_conflicts(
    api_client: AsyncClient, db_session: AsyncSession, seeded: SeededFamily,
):
    seeded.season.is_active = False
    await db_session.commit()
    resp = await api_client.post(PATH, json=_body(seeded), headers=_headers(seeded.parent))
    assert resp.status_code == 409, resp.text
    assert "赛季" in resp.text


# ---- 5. 结算路径不受影响:无模板实例照常可接取 ----


async def test_ephemeral_task_can_be_started_by_child(
    api_client: AsyncClient, db_session: AsyncSession, seeded: SeededFamily,
):
    """_deposit_of 只读实例 time_deposit,COOP 判定对 template=None 有兜底 ——
    因此无模板实例的接取/扣押金链路不需要任何额外分支。"""
    seeded.child.time_coin_balance = 100  # 押金要先有余额可扣
    await db_session.commit()

    created = await api_client.post(
        PATH, json=_body(seeded, time_deposit=5), headers=_headers(seeded.parent),
    )
    assert created.status_code == 200, created.text
    task_id = created.json()["data"]["id"]

    started = await api_client.post(
        f"{PATH}/{task_id}/start", headers=_headers(seeded.child_account),
    )
    assert started.status_code == 200, started.text
    body = started.json()["data"]
    assert body["status"] == TaskStatus.IN_PROGRESS
    assert body["type"] == "DAILY"  # 无模板穿读 → 既有 DAILY 兜底


async def _list_ids(api_client: AsyncClient, account) -> set[str]:
    resp = await api_client.get(
        PATH, params={"page_size": 200}, headers=_headers(account),
    )
    assert resp.status_code == 200, resp.text
    return {item["id"] for item in resp.json()["data"]["items"]}