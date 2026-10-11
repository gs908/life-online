"""
FastAPI 入口。

- 装配 CORS
- 注册 lifespan(初始化 logging、scheduler)
- 挂载 /api/v1 路由
- 安装全局异常处理
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.common.logging import configure_logging, get_logger
from app.config import settings
from app.middleware import install_exception_handlers
from app.workers.scheduler import build_scheduler


async def _check_storage_reachable(log) -> None:
    """MinIO 可达性预检(DEV-28):只告警、不阻断启动。

    - 未配置 → 提示补配置/切 local(请求路径 factory 会给 503);
    - 配置但连不上 → 给出可操作修复提示(启动 MinIO / 切 local);
    - 连得上 → 顺带执行 ensure_bucket 建好 bucket。
    MinIO 在应用之后才启动的场景无需重启:每次上传前都会重试 ensure_bucket,
    连通后自动恢复。
    """
    if settings.storage.provider.lower() != "minio":
        return
    m = settings.storage.minio
    if not m.is_configured:
        log.warning(
            "storage provider=minio 但 MINIO_ENDPOINT / MINIO_ACCESS_KEY / MINIO_SECRET_KEY"
            " 未配置,上传接口将返回 503;请补全配置或切换 STORAGE_PROVIDER=local"
        )
        return
    try:
        from app.common.storage.factory import get_storage

        storage = get_storage()
        await storage.ensure_bucket()
        log.info("minio storage ready", endpoint=m.endpoint, bucket=storage.bucket)
    except Exception as e:  # noqa: BLE001 - 启动预检:任何失败都只告警,不允许阻断启动
        log.warning(
            "MinIO 不可达,上传接口将返回 503(待 MinIO 启动后自动恢复,无需重启):"
            " 请启动 MinIO(本地可用 docker: docker run -d -p 9000:9000 "
            "-e MINIO_ROOT_USER=... -e MINIO_ROOT_PASSWORD=... minio/minio server /data)"
            " 或切换 STORAGE_PROVIDER=local",
            endpoint=m.endpoint,
            error=repr(e),
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """应用启动 / 关闭钩子。"""
    configure_logging(settings.app.log_level)
    log = get_logger("app.lifespan")
    log.info(
        "starting",
        name=settings.app.name,
        host=settings.app.host,
        port=settings.app.port,
        debug=settings.app.debug,
    )

    scheduler = build_scheduler()
    scheduler.start()
    log.info("scheduler started")

    await _check_storage_reachable(log)

    try:
        yield
    finally:
        scheduler.shutdown(wait=False)
        log.info("scheduler stopped")
        log.info("shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Life Online API",
        version="0.0.0",
        debug=settings.app.debug,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.app.cors_origins or ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    install_exception_handlers(app)
    app.include_router(api_router, prefix="/api/v1")
    if settings.storage.provider.lower() in {"local", "filestorage", "file"}:
        Path(settings.storage.local.root_path).mkdir(parents=True, exist_ok=True)
        app.mount(
            settings.storage.local.public_base_url,
            StaticFiles(directory=settings.storage.local.root_path),
            name="local-files",
        )
    return app


app = create_app()
