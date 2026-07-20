"""健康检查端点。

- /api/v1/health        基础 ping
- /api/v1/health/ready  就绪探针(后续会检查 DB / MinIO / LLM 是否可达)
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.config import settings
from app.schemas.common import ApiResponse, ok

router = APIRouter(prefix="/health", tags=["health"])


class HealthResponse(BaseModel):
    status: str
    name: str
    version: str
    debug: bool


@router.get("", response_model=ApiResponse[HealthResponse], summary="基础健康检查")
async def healthcheck() -> ApiResponse[HealthResponse]:
    return ok(HealthResponse(
        status="ok",
        name=settings.app.name,
        version="0.0.0",
        debug=settings.app.debug,
    ))


@router.get("/ready", response_model=ApiResponse[dict], summary="就绪探针")
async def ready() -> ApiResponse[dict]:
    # TODO(Round 2+): 实际检查 DB / MinIO / LLM 可达性
    return ok({"ready": True})
