"""任务路由:CRUD + 状态机操作。"""
from __future__ import annotations

from fastapi import APIRouter, Query

from app.deps import CurrentUser, DBSession, GuildMasterOnly
from app.models.enums import TaskStatus
from app.schemas.common import ApiResponse, PageQuery, PageResult, ok
from app.schemas.task import (
    TaskApproveRequest,
    TaskCreate,
    TaskRead,
    TaskSubmitRequest,
)
from app.services import task_service
from app.services.upload_service import build_access_url

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _to_read(t) -> TaskRead:
    proof_url = None
    if t.proof_object_key:
        try:
            proof_url = build_access_url(t.proof_object_key)
        except Exception:
            proof_url = None
    return TaskRead(
        id=t.id, family_id=t.family_id, season_id=t.season_id,
        creator_id=t.creator_id, target_user_id=t.target_user_id, assignee_id=t.assignee_id,
        title=t.title, description=t.description, lore_snippet=t.lore_snippet,
        xp_reward=t.xp_reward, type=t.type, status=t.status,
        deadline=t.deadline, required_start_time=t.required_start_time,
        proof_url=proof_url, rating=t.rating,
        started_at=t.started_at, submitted_at=t.submitted_at, completed_at=t.completed_at,
        reminder_message=t.reminder_message, reminder_minutes_before=t.reminder_minutes_before,
        time_deposit=t.time_deposit,
        created_at=t.created_at, updated_at=t.updated_at,
    )


@router.get("", response_model=ApiResponse[PageResult[TaskRead]], summary="任务列表")
async def list_tasks(
    db: DBSession, user: CurrentUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    season_id: str | None = Query(default=None),
    status: TaskStatus | None = Query(default=None),
    assignee_id: str | None = Query(default=None),
) -> ApiResponse[PageResult[TaskRead]]:
    query = PageQuery(page=page, page_size=page_size)
    items, total = await task_service.list_tasks(
        db, family_id=user.family_id,
        season_id=season_id, status=status, assignee_id=assignee_id,
        offset=query.offset, limit=query.page_size,
    )
    return ok(PageResult(
        items=[_to_read(t) for t in items],
        total=total,
        page=query.page,
        page_size=query.page_size,
    ))


@router.get("/{task_id}", response_model=ApiResponse[TaskRead], summary="任务详情")
async def get_task(task_id: str, db: DBSession, user: CurrentUser) -> ApiResponse[TaskRead]:
    t = await task_service.get_task(db, task_id)
    if t.family_id != user.family_id:
        from app.common.exceptions import PermissionDeniedError
        raise PermissionDeniedError("只能查看自己家庭的任务")
    return ok(_to_read(t))


@router.post("", response_model=ApiResponse[TaskRead], summary="创建任务(父母)")
async def create_task(
    body: TaskCreate, db: DBSession, user: GuildMasterOnly,
) -> ApiResponse[TaskRead]:
    data = body.model_dump()
    t = await task_service.create_task(
        db, family_id=user.family_id, creator_id=user.id, **data,
    )
    return ok(_to_read(t))


@router.delete("/{task_id}", response_model=ApiResponse[dict], summary="删除任务(父母)")
async def delete_task(task_id: str, db: DBSession, user: GuildMasterOnly) -> ApiResponse[dict]:
    await task_service.delete_task(db, task_id=task_id, family_id=user.family_id)
    return ok({"ok": True})


@router.post("/{task_id}/start", response_model=ApiResponse[TaskRead], summary="孩子接取任务")
async def start_task(
    task_id: str, db: DBSession, user: CurrentUser,
) -> ApiResponse[TaskRead]:
    t = await task_service.start_task(db, task_id=task_id, user=user)
    return ok(_to_read(t))


@router.post("/{task_id}/submit", response_model=ApiResponse[TaskRead], summary="孩子提交")
async def submit_task(
    task_id: str, body: TaskSubmitRequest, db: DBSession, user: CurrentUser,
) -> ApiResponse[TaskRead]:
    t = await task_service.submit_task(
        db, task_id=task_id, user=user, proof_object_key=body.proof_object_key,
    )
    return ok(_to_read(t))


@router.post("/{task_id}/approve", response_model=ApiResponse[TaskRead], summary="父母审核")
async def approve_task(
    task_id: str, body: TaskApproveRequest, db: DBSession, user: GuildMasterOnly,
) -> ApiResponse[TaskRead]:
    t, _assignee, _info = await task_service.approve_task(
        db, task_id=task_id, family_id=user.family_id, rating=body.rating, comment=body.comment,
    )
    return ok(_to_read(t))


@router.post("/{task_id}/abandon", response_model=ApiResponse[TaskRead], summary="孩子放弃")
async def abandon_task(
    task_id: str, db: DBSession, user: CurrentUser,
) -> ApiResponse[TaskRead]:
    t, _u, _refund = await task_service.abandon_task(db, task_id=task_id, user=user)
    return ok(_to_read(t))
