"""
开发期非微信登录冒烟测试(DEV-5)。

覆盖:
- `DEV_LOGIN_ENABLED=false`(默认/生产口径)时,`/sys/auth/dev-login` 一律拒绝,
  不需要连数据库,始终会执行,不受 `db_ready` 影响。
- `DEV_LOGIN_ENABLED=true` 时,家长 / 孩子两种角色都能拿到可用的 token,并且
  重复调用返回同一个账号(幂等,不会每次都在数据库里堆新家庭)。

通过 `app.dependency_overrides` 覆盖 `get_settings` 依赖来切换开关,不依赖真实
环境变量,也不影响其它测试用例读到的全局 `settings`。
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import AsyncIterator

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.config import get_settings
from app.main import app
from app.models.enums import UserRole


def _fake_settings(*, login_enabled: bool) -> SimpleNamespace:
    return SimpleNamespace(dev=SimpleNamespace(login_enabled=login_enabled))


@pytest_asyncio.fixture
async def dev_login_disabled() -> AsyncIterator[None]:
    app.dependency_overrides[get_settings] = lambda: _fake_settings(login_enabled=False)
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_settings, None)


@pytest_asyncio.fixture
async def dev_login_enabled() -> AsyncIterator[None]:
    app.dependency_overrides[get_settings] = lambda: _fake_settings(login_enabled=True)
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_settings, None)


async def test_dev_login_rejected_when_disabled(
    api_client: AsyncClient, dev_login_disabled: None
) -> None:
    resp = await api_client.post("/api/v1/sys/auth/dev-login", json={"role": "ADVENTURER"})
    assert resp.status_code == 403


async def test_dev_login_rejected_by_default(api_client: AsyncClient) -> None:
    """不覆盖任何依赖时,走进程真实配置,默认值也必须是关闭的。"""
    resp = await api_client.post("/api/v1/sys/auth/dev-login", json={"role": "ADVENTURER"})
    assert resp.status_code == 403


@pytest.mark.db
async def test_dev_login_as_parent_when_enabled(
    api_client: AsyncClient, dev_login_enabled: None, db_ready: bool
) -> None:
    resp = await api_client.post("/api/v1/sys/auth/dev-login", json={"role": "GUILD_MASTER"})
    assert resp.status_code == 200
    tokens = resp.json()["data"]
    assert tokens["access_token"]

    me_resp = await api_client.get(
        "/api/v1/sys/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["data"]["role"] == UserRole.GUILD_MASTER.value


@pytest.mark.db
async def test_dev_login_as_child_when_enabled(
    api_client: AsyncClient, dev_login_enabled: None, db_ready: bool
) -> None:
    resp = await api_client.post("/api/v1/sys/auth/dev-login", json={"role": "ADVENTURER"})
    assert resp.status_code == 200
    tokens = resp.json()["data"]

    me_resp = await api_client.get(
        "/api/v1/sys/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert me_resp.status_code == 200
    data = me_resp.json()["data"]
    assert data["role"] == UserRole.ADVENTURER.value
    assert data["child_id"] is not None


@pytest.mark.db
async def test_dev_login_is_idempotent(
    api_client: AsyncClient, dev_login_enabled: None, db_ready: bool
) -> None:
    first = await api_client.post("/api/v1/sys/auth/dev-login", json={"role": "ADVENTURER"})
    second = await api_client.post("/api/v1/sys/auth/dev-login", json={"role": "ADVENTURER"})

    first_id = first.json()["data"]
    second_id = second.json()["data"]

    async def account_id(tokens: dict) -> str:
        r = await api_client.get(
            "/api/v1/sys/auth/me",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        return r.json()["data"]["id"]

    assert await account_id(first_id) == await account_id(second_id)
