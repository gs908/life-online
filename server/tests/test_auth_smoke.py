"""
最小 API 冒烟测试:认证相关基础路径。

覆盖:
- 用种子数据(家长 + 孩子)签发 token,调用 `/sys/auth/me` 能拿到对应身份。
- `/sys/auth/refresh` 能用 refresh token 换到新的 access token。
- 未带 Authorization 头访问受保护接口应被拒绝。

需要可连接的数据库(远程优先),不可达时该模块内用例会被 `db_ready` fixture 跳过。
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.dev.seed import SeededFamily
from app.models.enums import UserRole
from app.services import auth_service

pytestmark = pytest.mark.db


async def test_me_as_parent(api_client: AsyncClient, seeded_family: SeededFamily) -> None:
    tokens = auth_service.issue_token_pair(seeded_family.parent)

    resp = await api_client.get(
        "/api/v1/sys/auth/me",
        headers={"Authorization": f"Bearer {tokens.access_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["id"] == seeded_family.parent.id
    assert data["family_id"] == seeded_family.family.id
    assert data["role"] == UserRole.GUILD_MASTER.value
    assert data["child_id"] is None


async def test_me_as_child(api_client: AsyncClient, seeded_family: SeededFamily) -> None:
    tokens = auth_service.issue_token_pair(seeded_family.child_account)

    resp = await api_client.get(
        "/api/v1/sys/auth/me",
        headers={"Authorization": f"Bearer {tokens.access_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["id"] == seeded_family.child_account.id
    assert data["role"] == UserRole.ADVENTURER.value
    assert data["child_id"] == seeded_family.child.id


async def test_refresh_issues_new_access_token(
    api_client: AsyncClient, seeded_family: SeededFamily
) -> None:
    tokens = auth_service.issue_token_pair(seeded_family.parent)

    resp = await api_client.post(
        "/api/v1/sys/auth/refresh", json={"refresh_token": tokens.refresh_token}
    )
    assert resp.status_code == 200
    new_tokens = resp.json()["data"]
    assert new_tokens["access_token"]
    assert new_tokens["refresh_token"]


async def test_me_without_token_is_unauthorized(api_client: AsyncClient) -> None:
    resp = await api_client.get("/api/v1/sys/auth/me")
    assert resp.status_code == 401
