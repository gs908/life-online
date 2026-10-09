"""
时间币 / 上传 / AI 闭环冒烟测试(DEV-9)。

覆盖:
- 时间币配置读取/更新(`/scn/time-configs/me`),孩子无权更新。
- 时间币流水查询与人工调整(`/scn/time-coin-logs`),写操作仅父母、跨家庭隔离。
- 每日重置与时间币配置联动(`coin_service.reset_daily_allowance` 按配置里的
  当日特例/默认额度写回余额,并落一条 DAILY_RESET 流水)。
- 上传接口在 local 存储模式下可用,返回的 `access_url` 可直接给前端展示。
- AI 接口(`/scn/ai/generate-quest`、`/scn/ai/evaluate-proof`)在 LLM 未配置时
  统一返回明确的 503,而不是 500 或连接超时。

需要可连接的数据库(远程优先),不可达时该模块内用例会被 `db_ready` fixture 跳过。
LLM/存储的"未配置"分支不需要真实网络访问,可以在无外网的沙箱里稳定执行。
"""
from __future__ import annotations

from datetime import date

import pytest
from httpx import AsyncClient

from app.common.llm.factory import get_llm_client
from app.common.storage.factory import get_storage
from app.config import settings
from app.dev.seed import SeededFamily
from app.models.enums import CoinTransactionType, UploadPurpose
from app.models.sys_child import SysChild
from app.services import auth_service, coin_service

pytestmark = pytest.mark.db


def _auth_headers(account) -> dict[str, str]:
    tokens = auth_service.issue_token_pair(account)
    return {"Authorization": f"Bearer {tokens.access_token}"}


async def test_time_config_get_and_update(
    api_client: AsyncClient, seeded_family: SeededFamily
) -> None:
    parent_headers = _auth_headers(seeded_family.parent)
    child_headers = _auth_headers(seeded_family.child_account)

    resp = await api_client.get("/api/v1/scn/time-configs/me", headers=parent_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["family_id"] == seeded_family.family.id

    resp = await api_client.put(
        "/api/v1/scn/time-configs/me",
        headers=parent_headers,
        json={"default_daily_allowance": 150, "exceptions": [{"day_of_week": 0, "coin_amount": 300}]},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["default_daily_allowance"] == 150
    assert data["exceptions"] == [{"day_of_week": 0, "coin_amount": 300}]

    # 孩子无权更新配置
    resp = await api_client.put(
        "/api/v1/scn/time-configs/me",
        headers=child_headers,
        json={"default_daily_allowance": 999},
    )
    assert resp.status_code == 403


async def test_coin_logs_list_and_adjust_with_family_isolation(
    api_client: AsyncClient, seeded_family: SeededFamily
) -> None:
    parent_headers = _auth_headers(seeded_family.parent)
    child_headers = _auth_headers(seeded_family.child_account)

    resp = await api_client.post(
        "/api/v1/scn/time-coin-logs/adjust",
        headers=parent_headers,
        json={"child_id": seeded_family.child_account.id, "amount": 20, "note": "奖励"},
    )
    assert resp.status_code == 200
    tx = resp.json()["data"]
    assert tx["amount"] == 20
    assert tx["type"] == CoinTransactionType.MANUAL_ADJUST.value

    # 孩子无权人工调整
    resp = await api_client.post(
        "/api/v1/scn/time-coin-logs/adjust",
        headers=child_headers,
        json={"child_id": seeded_family.child_account.id, "amount": 20},
    )
    assert resp.status_code == 403

    resp = await api_client.get("/api/v1/scn/time-coin-logs", headers=parent_headers)
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert any(i["id"] == tx["id"] for i in items)
    assert all(i["family_id"] == seeded_family.family.id for i in items)


async def test_daily_reset_uses_time_config(
    db_ready: bool, seeded_family: SeededFamily
) -> None:
    from app.common.db.engine import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        tc = await coin_service.get_or_create_time_config(db, seeded_family.family.id)
        tc.default_daily_allowance = 42
        await db.commit()

        child = await db.get(SysChild, seeded_family.child.id)
        child.time_coin_balance = 5
        child.last_login_date = None
        await db.flush()

        today = date.today()
        allowance = await coin_service.reset_daily_allowance(db, child, today)
        await db.commit()

    assert allowance == 42
    assert child.time_coin_balance == 42
    assert child.last_login_date == today
    assert child.daily_abandon_count == 0


async def test_upload_task_proof_with_local_storage(
    api_client: AsyncClient, seeded_family: SeededFamily, monkeypatch, tmp_path
) -> None:
    """local 存储不需要任何外部配置,始终可用 —— 是 MinIO 未配置时的降级路径。"""
    get_storage.cache_clear()
    monkeypatch.setattr(settings.storage, "provider", "local")
    monkeypatch.setattr(settings.storage.local, "root_path", str(tmp_path))
    try:
        resp = await api_client.post(
            "/api/v1/sys/uploads",
            headers=_auth_headers(seeded_family.child_account),
            data={"purpose": UploadPurpose.TASK_PROOF.value},
            files={"file": ("proof.jpg", b"fake-image-bytes", "image/jpeg")},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["purpose"] == UploadPurpose.TASK_PROOF.value
        assert data["family_id"] == seeded_family.family.id
        assert data["access_url"], "前端需要一个可直接展示的 access_url"
    finally:
        get_storage.cache_clear()


async def test_upload_returns_503_when_minio_not_configured(
    api_client: AsyncClient, seeded_family: SeededFamily, monkeypatch
) -> None:
    get_storage.cache_clear()
    monkeypatch.setattr(settings.storage, "provider", "minio")
    monkeypatch.setattr(settings.storage.minio, "endpoint", "")
    monkeypatch.setattr(settings.storage.minio, "access_key", "")
    monkeypatch.setattr(settings.storage.minio, "secret_key", "")
    try:
        resp = await api_client.post(
            "/api/v1/sys/uploads",
            headers=_auth_headers(seeded_family.child_account),
            data={"purpose": UploadPurpose.TASK_PROOF.value},
            files={"file": ("proof.jpg", b"fake-image-bytes", "image/jpeg")},
        )
        assert resp.status_code == 503
        assert resp.json()["data"]["error_code"] == "service_unavailable"
    finally:
        get_storage.cache_clear()


async def test_ai_endpoints_return_503_when_llm_not_configured(
    api_client: AsyncClient, seeded_family: SeededFamily, monkeypatch
) -> None:
    get_llm_client.cache_clear()
    monkeypatch.setattr(settings.llm, "base_url", "")
    monkeypatch.setattr(settings.llm, "api_key", "")
    monkeypatch.setattr(settings.llm, "model", "")
    parent_headers = _auth_headers(seeded_family.parent)
    try:
        resp = await api_client.post(
            "/api/v1/scn/ai/generate-quest",
            headers=parent_headers,
            json={"topic": "打扫房间", "child_level": 3},
        )
        assert resp.status_code == 503
        assert resp.json()["data"]["error_code"] == "service_unavailable"

        resp = await api_client.post(
            "/api/v1/scn/ai/evaluate-proof",
            headers=parent_headers,
            json={"task_title": "打扫房间", "image_data_url": "data:image/png;base64,AAAA"},
        )
        assert resp.status_code == 503
        assert resp.json()["data"]["error_code"] == "service_unavailable"

        # 孩子无权调用 AI 管理接口(与父母专属接口权限保持一致)
        resp = await api_client.post(
            "/api/v1/scn/ai/generate-quest",
            headers=_auth_headers(seeded_family.child_account),
            json={"topic": "打扫房间"},
        )
        assert resp.status_code == 403
    finally:
        get_llm_client.cache_clear()
