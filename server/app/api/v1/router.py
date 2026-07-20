"""v1 路由聚合。"""
from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    ai,
    auth,
    coins,
    families,
    health,
    privileges,
    redemptions,
    seasons,
    tasks,
    themes,
    time_config,
    uploads,
    users,
)

api_router = APIRouter()

# 子 router 内部已经定义了 prefix(例如 AI 路由 prefix='/ai'),
# 这里 include 时不要再加 prefix,只传 tags。

api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, tags=["auth"])
api_router.include_router(users.router, tags=["users"])
api_router.include_router(families.router, tags=["families"])
api_router.include_router(seasons.router, tags=["seasons"])
api_router.include_router(tasks.router, tags=["tasks"])
api_router.include_router(themes.router, tags=["themes"])
api_router.include_router(coins.router, tags=["coins"])
api_router.include_router(privileges.router, tags=["privileges"])
api_router.include_router(redemptions.router, tags=["redemptions"])
api_router.include_router(time_config.router, tags=["time-config"])
api_router.include_router(uploads.router, tags=["uploads"])
api_router.include_router(ai.router, tags=["ai"])
