"""
Web 管理后端冒烟测试(DEV-6):家庭成员查看 / 孩子账号创建更新 / 当前用户资料 / 权限隔离。

覆盖:
- 家长可查看自己家庭成员(`/sys/families/me`),结构里家长/孩子分组。
- 家长可创建孩子冒险者账号(`/sys/accounts/adventurers`),孩子角色不能创建。
- 家长可更新自己家庭下孩子的基础信息(昵称/头像),孩子角色不能调用该接口。
- 家长不能更新别的家庭的孩子(跨家庭隔离,统一返回 404,不泄露账号是否存在)。
- 当前用户资料查看/更新(`/sys/accounts/me`)对家长和孩子都可用。

需要可连接的数据库(远程优先),不可达时该模块内用例会被 `db_ready` fixture 跳过。
"""
from __future__ import annotations

from typing import AsyncIterator

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.dev.seed import SeededFamily, cleanup_family, seed_basic_family
from app.services import auth_service

pytestmark = pytest.mark.db


def _auth_headers(account) -> dict[str, str]:
    tokens = auth_service.issue_token_pair(account)
    return {"Authorization": f"Bearer {tokens.access_token}"}


@pytest_asyncio.fixture
async def other_family(db_session: AsyncSession) -> AsyncIterator[SeededFamily]:
    """第二个家庭,专门用于跨家庭隔离断言。"""
    seeded = await seed_basic_family(db_session, suffix="other")
    try:
        yield seeded
    finally:
        await cleanup_family(db_session, seeded.family.id)


async def test_family_me_lists_own_members_only(
    api_client: AsyncClient, seeded_family: SeededFamily, other_family: SeededFamily
) -> None:
    resp = await api_client.get(
        "/api/v1/sys/families/me", headers=_auth_headers(seeded_family.parent)
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["family"]["id"] == seeded_family.family.id

    gm_ids = {m["id"] for m in data["guild_masters"]}
    adv_ids = {m["id"] for m in data["adventurers"]}
    assert gm_ids == {seeded_family.parent.id}
    assert adv_ids == {seeded_family.child_account.id}
    # 另一个家庭的成员不应出现
    assert other_family.parent.id not in gm_ids
    assert other_family.child_account.id not in adv_ids


async def test_family_me_as_child_scoped_to_own_family(
    api_client: AsyncClient, seeded_family: SeededFamily
) -> None:
    resp = await api_client.get(
        "/api/v1/sys/families/me", headers=_auth_headers(seeded_family.child_account)
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["family"]["id"] == seeded_family.family.id


async def test_parent_can_create_adventurer(
    api_client: AsyncClient, seeded_family: SeededFamily
) -> None:
    resp = await api_client.post(
        "/api/v1/sys/accounts/adventurers",
        json={"name": "新孩子", "avatar": "🧑"},
        headers=_auth_headers(seeded_family.parent),
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["name"] == "新孩子"
    assert data["role"] == "ADVENTURER"
    assert data["family_id"] == seeded_family.family.id


async def test_child_cannot_create_adventurer(
    api_client: AsyncClient, seeded_family: SeededFamily
) -> None:
    resp = await api_client.post(
        "/api/v1/sys/accounts/adventurers",
        json={"name": "越权创建"},
        headers=_auth_headers(seeded_family.child_account),
    )
    assert resp.status_code == 403


async def test_parent_can_update_own_child(
    api_client: AsyncClient, seeded_family: SeededFamily
) -> None:
    resp = await api_client.patch(
        f"/api/v1/sys/accounts/adventurers/{seeded_family.child_account.id}",
        json={"name": "改名后的孩子", "avatar": "🦸"},
        headers=_auth_headers(seeded_family.parent),
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["id"] == seeded_family.child_account.id
    assert data["name"] == "改名后的孩子"
    assert data["avatar"] == "🦸"


async def test_child_cannot_update_adventurer(
    api_client: AsyncClient, seeded_family: SeededFamily
) -> None:
    resp = await api_client.patch(
        f"/api/v1/sys/accounts/adventurers/{seeded_family.child_account.id}",
        json={"name": "越权改名"},
        headers=_auth_headers(seeded_family.child_account),
    )
    assert resp.status_code == 403


async def test_parent_cannot_update_child_in_other_family(
    api_client: AsyncClient, seeded_family: SeededFamily, other_family: SeededFamily
) -> None:
    resp = await api_client.patch(
        f"/api/v1/sys/accounts/adventurers/{other_family.child_account.id}",
        json={"name": "跨家庭改名"},
        headers=_auth_headers(seeded_family.parent),
    )
    assert resp.status_code == 404


async def test_me_profile_get_and_patch_for_parent(
    api_client: AsyncClient, seeded_family: SeededFamily
) -> None:
    get_resp = await api_client.get(
        "/api/v1/sys/accounts/me", headers=_auth_headers(seeded_family.parent)
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["data"]["id"] == seeded_family.parent.id

    patch_resp = await api_client.patch(
        "/api/v1/sys/accounts/me",
        json={"name": "更新后的家长"},
        headers=_auth_headers(seeded_family.parent),
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["data"]["name"] == "更新后的家长"


async def test_me_profile_get_and_patch_for_child(
    api_client: AsyncClient, seeded_family: SeededFamily
) -> None:
    get_resp = await api_client.get(
        "/api/v1/sys/accounts/me", headers=_auth_headers(seeded_family.child_account)
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["data"]["child_id"] == seeded_family.child.id

    patch_resp = await api_client.patch(
        "/api/v1/sys/accounts/me",
        json={"avatar": "🐉"},
        headers=_auth_headers(seeded_family.child_account),
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["data"]["avatar"] == "🐉"
