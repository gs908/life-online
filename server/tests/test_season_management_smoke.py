"""赛季管理冒烟测试(DEV-7):列表/详情/创建/更新/删除/激活 + 单一激活赛季 + 跨家庭隔离 + 历史统计。

覆盖:
- 家长可完成赛季创建 -> 详情 -> 更新 -> 激活 -> 删除的完整闭环。
- 创建/激活新赛季会自动使同家庭下原激活赛季下线,任意时刻家庭内最多一个 `is_active=True`。
- 赛季详情/更新/删除/激活对别的家庭的赛季一律返回 404(不泄露赛季是否存在于别的家庭)。
- 孩子角色调用写接口(创建/更新/删除/激活)返回 403。
- 历史统计接口返回每个赛季的任务总数/完成数/已发放 XP 总和,供 Web 管理台历史面板展示。
- 赛季与任务模板/任务实例的关联规则:删除赛季会级联删除挂在它下面的任务模板与任务实例。

需要可连接的数据库(远程优先),不可达时该模块内用例会被 `db_ready` fixture 跳过。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import AsyncIterator

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dev.seed import SeededFamily, cleanup_family, seed_basic_family
from app.models.enums import TaskStatus
from app.models.scn_season import ScnSeason
from app.models.scn_task_instance import ScnTaskInstance
from app.models.scn_task_template import ScnTaskTemplate
from app.services import auth_service

pytestmark = pytest.mark.db


def _auth_headers(account) -> dict[str, str]:
    tokens = auth_service.issue_token_pair(account)
    return {"Authorization": f"Bearer {tokens.access_token}"}


def _iso(dt: datetime) -> str:
    return dt.isoformat()


@pytest_asyncio.fixture
async def other_family(db_session: AsyncSession) -> AsyncIterator[SeededFamily]:
    """第二个家庭,专门用于跨家庭隔离断言。"""
    seeded = await seed_basic_family(db_session, suffix="season-other")
    try:
        yield seeded
    finally:
        await cleanup_family(db_session, seeded.family.id)


async def test_parent_full_season_lifecycle(
    api_client: AsyncClient, seeded_family: SeededFamily
) -> None:
    headers = _auth_headers(seeded_family.parent)

    create_resp = await api_client.post(
        "/api/v1/scn/seasons",
        json={
            "name": "冰霜赛季",
            "theme_id": "FROSTBOUND",
            "narrative_context": "严冬降临",
            "start_date": _iso(datetime.now(timezone.utc)),
        },
        headers=headers,
    )
    assert create_resp.status_code == 200
    new_season = create_resp.json()["data"]
    assert new_season["is_active"] is True

    get_resp = await api_client.get(f"/api/v1/scn/seasons/{new_season['id']}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["data"]["name"] == "冰霜赛季"

    patch_resp = await api_client.patch(
        f"/api/v1/scn/seasons/{new_season['id']}",
        json={"name": "冰霜赛季-改"},
        headers=headers,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["data"]["name"] == "冰霜赛季-改"

    delete_resp = await api_client.delete(f"/api/v1/scn/seasons/{new_season['id']}", headers=headers)
    assert delete_resp.status_code == 200
    assert delete_resp.json()["data"]["deleted"] is True

    get_after_delete = await api_client.get(f"/api/v1/scn/seasons/{new_season['id']}", headers=headers)
    assert get_after_delete.status_code == 404


async def test_only_one_active_season_per_family(
    api_client: AsyncClient, seeded_family: SeededFamily, db_session: AsyncSession
) -> None:
    headers = _auth_headers(seeded_family.parent)

    create_resp = await api_client.post(
        "/api/v1/scn/seasons",
        json={"name": "新赛季", "start_date": _iso(datetime.now(timezone.utc))},
        headers=headers,
    )
    assert create_resp.status_code == 200
    new_season_id = create_resp.json()["data"]["id"]

    rows = (
        await db_session.execute(
            select(ScnSeason).where(
                ScnSeason.family_id == seeded_family.family.id, ScnSeason.is_active.is_(True)
            )
        )
    ).scalars().all()
    assert [r.id for r in rows] == [new_season_id]

    old_season_resp = await api_client.get(
        f"/api/v1/scn/seasons/{seeded_family.season.id}", headers=headers
    )
    assert old_season_resp.json()["data"]["is_active"] is False

    activate_resp = await api_client.post(
        f"/api/v1/scn/seasons/{seeded_family.season.id}/activate", headers=headers
    )
    assert activate_resp.status_code == 200
    assert activate_resp.json()["data"]["is_active"] is True

    rows_after = (
        await db_session.execute(
            select(ScnSeason).where(
                ScnSeason.family_id == seeded_family.family.id, ScnSeason.is_active.is_(True)
            )
        )
    ).scalars().all()
    assert [r.id for r in rows_after] == [seeded_family.season.id]


async def test_season_cross_family_isolation(
    api_client: AsyncClient, seeded_family: SeededFamily, other_family: SeededFamily
) -> None:
    headers = _auth_headers(seeded_family.parent)
    other_season_id = other_family.season.id

    get_resp = await api_client.get(f"/api/v1/scn/seasons/{other_season_id}", headers=headers)
    assert get_resp.status_code == 404

    patch_resp = await api_client.patch(
        f"/api/v1/scn/seasons/{other_season_id}", json={"name": "越权改名"}, headers=headers
    )
    assert patch_resp.status_code == 404

    activate_resp = await api_client.post(
        f"/api/v1/scn/seasons/{other_season_id}/activate", headers=headers
    )
    assert activate_resp.status_code == 404

    delete_resp = await api_client.delete(f"/api/v1/scn/seasons/{other_season_id}", headers=headers)
    assert delete_resp.status_code == 404

    list_resp = await api_client.get("/api/v1/scn/seasons", headers=headers)
    assert list_resp.status_code == 200
    listed_ids = {s["id"] for s in list_resp.json()["data"]}
    assert other_season_id not in listed_ids


async def test_child_cannot_write_seasons(
    api_client: AsyncClient, seeded_family: SeededFamily
) -> None:
    headers = _auth_headers(seeded_family.child_account)

    create_resp = await api_client.post(
        "/api/v1/scn/seasons",
        json={"name": "孩子创建", "start_date": _iso(datetime.now(timezone.utc))},
        headers=headers,
    )
    assert create_resp.status_code == 403

    patch_resp = await api_client.patch(
        f"/api/v1/scn/seasons/{seeded_family.season.id}", json={"name": "越权改名"}, headers=headers
    )
    assert patch_resp.status_code == 403

    activate_resp = await api_client.post(
        f"/api/v1/scn/seasons/{seeded_family.season.id}/activate", headers=headers
    )
    assert activate_resp.status_code == 403

    delete_resp = await api_client.delete(
        f"/api/v1/scn/seasons/{seeded_family.season.id}", headers=headers
    )
    assert delete_resp.status_code == 403

    # 只读接口对孩子角色开放
    get_resp = await api_client.get(f"/api/v1/scn/seasons/{seeded_family.season.id}", headers=headers)
    assert get_resp.status_code == 200


async def test_season_history_stats(
    api_client: AsyncClient, seeded_family: SeededFamily, db_session: AsyncSession
) -> None:
    seeded_family.task_instance.status = TaskStatus.COMPLETED
    seeded_family.task_instance.xp_awarded = 42
    await db_session.commit()

    headers = _auth_headers(seeded_family.parent)
    resp = await api_client.get("/api/v1/scn/seasons/history", headers=headers)
    assert resp.status_code == 200
    rows = resp.json()["data"]
    row = next(r for r in rows if r["season"]["id"] == seeded_family.season.id)
    assert row["total_tasks"] == 1
    assert row["completed_tasks"] == 1
    assert row["total_xp"] == 42


async def test_deleting_season_cascades_task_templates_and_instances(
    seeded_family: SeededFamily, db_session: AsyncSession
) -> None:
    from app.services import season_service

    await season_service.delete_season(
        db_session, season_id=seeded_family.season.id, family_id=seeded_family.family.id
    )

    remaining_templates = (
        await db_session.execute(
            select(ScnTaskTemplate).where(ScnTaskTemplate.id == seeded_family.task_template.id)
        )
    ).scalar_one_or_none()
    remaining_instances = (
        await db_session.execute(
            select(ScnTaskInstance).where(ScnTaskInstance.id == seeded_family.task_instance.id)
        )
    ).scalar_one_or_none()
    assert remaining_templates is None
    assert remaining_instances is None
