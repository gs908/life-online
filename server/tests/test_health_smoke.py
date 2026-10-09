"""
最小 API 冒烟测试:健康检查。

不依赖数据库,验证 FastAPI app 能被正常创建并挂载 /api/v1 路由。
"""
from __future__ import annotations

from httpx import AsyncClient


async def test_healthcheck(api_client: AsyncClient) -> None:
    resp = await api_client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["status"] == "ok"


async def test_health_ready(api_client: AsyncClient) -> None:
    resp = await api_client.get("/api/v1/health/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["ready"] is True


async def test_docs_available(api_client: AsyncClient) -> None:
    resp = await api_client.get("/docs")
    assert resp.status_code == 200
