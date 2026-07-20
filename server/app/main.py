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
