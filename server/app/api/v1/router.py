"""v1 路由聚合。"""
from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    ai,
    auth,
    coins,
    evidence,
    families,
    health,
    privileges,
    redemptions,
    seasons,
    task_templates,
    tasks,
    template_library,
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
# DEV-60:任务要点 -> 任务建议(/scn/tasks/generate-from-brief),只回渲染建议、不入库。
api_router.include_router(tasks.brief_router, tags=["scn-tasks"])
api_router.include_router(tasks.proofs_router, tags=["scn-task-proofs"])
# 两套路由前缀同为 /scn/task-templates 但路径不重叠:
# tasks.templates_router 仅 /preview-deposit(DEV-34 块 C 押金预览);
# task_templates.router 为块 A 模板 CRUD 与 /{template_id}/... 操作。
api_router.include_router(tasks.templates_router, tags=["task-templates"])
api_router.include_router(task_templates.router, tags=["task-templates"])
api_router.include_router(template_library.router, tags=["template-library"])
api_router.include_router(themes.router, tags=["themes"])
api_router.include_router(coins.router, tags=["coins"])
api_router.include_router(privileges.router, tags=["privileges"])
api_router.include_router(redemptions.router, tags=["redemptions"])
api_router.include_router(time_config.router, tags=["time-config"])
api_router.include_router(uploads.router, tags=["uploads"])
api_router.include_router(evidence.router, tags=["scn-evidence"])
api_router.include_router(ai.router, tags=["ai"])
