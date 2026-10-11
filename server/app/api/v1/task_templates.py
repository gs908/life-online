"""任务模板路由:模板级 CRUD / 生命周期 / 再生成(docs/12 块 A)。

与 /scn/task-instances(实例状态机)分界:这里只操作模板与触发规则,
POST 只建模板+规则,不再强制建实例(创建后由生成器按需即时生成)。
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from app.common.exceptions import PermissionDeniedError
from app.deps import CurrentUser, DBSession, GuildMasterOnly
from app.models.enums import TaskType
from app.schemas.common import ApiResponse, ok
from app.schemas.task import (
    TaskTemplateCreate,
    TaskTemplateDeprecate,
    TaskTemplateRead,
    TaskTemplateRegenerate,
    TaskTemplateUpdate,
    TaskTriggerRead,
)
from app.services import task_template_service

router = APIRouter(prefix="/scn/task-templates", tags=["scn-task-templates"])


def _trigger_read(t) -> TaskTriggerRead:
    return TaskTriggerRead(
        id=t.id,
        template_id=t.template_id,
        kind=t.kind,
        cron_expr=t.cron_expr,
        weekdays=t.weekdays,
        day_of_month=t.day_of_month,
        generate_at=t.generate_at,
        starts_on=t.starts_on,
        ends_on=t.ends_on,
        is_active=t.is_active,
        created_at=t.created_at,
        updated_at=t.updated_at,
    )


def _to_read(t) -> TaskTemplateRead:
    return TaskTemplateRead(
        id=t.id,
        family_id=t.family_id,
        season_id=t.season_id,
        creator_account_id=t.creator_account_id,
        library_id=t.library_id,
        target_child_id=t.target_child_id,
        category=t.category,
        title=t.title,
        description=t.description,
        lore_snippet=t.lore_snippet,
        xp_reward=t.xp_reward,
        type=t.type,
        required_start_time=t.required_start_time,
        reminder_message=t.reminder_message,
        reminder_minutes_before=t.reminder_minutes_before,
        time_deposit=t.time_deposit,
        is_active=t.is_active,
        timed_mode=t.timed_mode,
        deadline_time=t.deadline_time,
        start_time=t.start_time,
        duration_minutes=t.duration_minutes,
        pool_policy=t.pool_policy,
        estimated_minutes=t.estimated_minutes,
        difficulty=t.difficulty,
        deprecated_at=t.deprecated_at,
        deprecated_reason=t.deprecated_reason,
        triggers=[_trigger_read(g) for g in t.triggers],
        created_at=t.created_at,
        updated_at=t.updated_at,
    )


async def _require_family_owner(db, user) -> None:
    """管理端权限守卫(当前口径:家庭 owner;平台管理员角色落地后替换)。"""
    if not await task_template_service.is_family_owner(
        db, family_id=user.family_id, account_id=user.id,
    ):
        raise PermissionDeniedError("该操作仅限家庭管理员(owner)")


@router.get("", response_model=ApiResponse[list[TaskTemplateRead]], summary="任务模板列表")
async def list_task_templates(
    db: DBSession, user: CurrentUser,
    season_id: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    type: TaskType | None = Query(default=None),
) -> ApiResponse[list[TaskTemplateRead]]:
    items = await task_template_service.list_templates(
        db,
        family_id=user.family_id,
        season_id=season_id,
        is_active=is_active,
        template_type=type.value if type is not None else None,
    )
    return ok([_to_read(t) for t in items])


@router.post("", response_model=ApiResponse[TaskTemplateRead], summary="创建任务模板(父母)")
async def create_task_template(
    body: TaskTemplateCreate, db: DBSession, user: GuildMasterOnly,
) -> ApiResponse[TaskTemplateRead]:
    template = await task_template_service.create_template(
        db, family_id=user.family_id, creator_id=user.id, payload=body,
    )
    return ok(_to_read(template))


@router.get("/{template_id}", response_model=ApiResponse[TaskTemplateRead], summary="任务模板详情")
async def get_task_template(
    template_id: str, db: DBSession, user: CurrentUser,
) -> ApiResponse[TaskTemplateRead]:
    template = await task_template_service.get_family_template(
        db, template_id=template_id, family_id=user.family_id,
    )
    return ok(_to_read(template))


@router.patch("/{template_id}", response_model=ApiResponse[TaskTemplateRead], summary="更新任务模板(父母)")
async def update_task_template(
    template_id: str, body: TaskTemplateUpdate, db: DBSession, user: GuildMasterOnly,
) -> ApiResponse[TaskTemplateRead]:
    template = await task_template_service.update_template(
        db, family_id=user.family_id, template_id=template_id, payload=body,
    )
    return ok(_to_read(template))


@router.post(
    "/{template_id}/deprecate",
    response_model=ApiResponse[TaskTemplateRead],
    summary="废弃任务模板(父母):停用+审计,既有实例不动",
)
async def deprecate_task_template(
    template_id: str, body: TaskTemplateDeprecate, db: DBSession, user: GuildMasterOnly,
) -> ApiResponse[TaskTemplateRead]:
    template = await task_template_service.deprecate_template(
        db, family_id=user.family_id, template_id=template_id, reason=body.reason,
    )
    return ok(_to_read(template))


@router.post(
    "/{template_id}/activate",
    response_model=ApiResponse[TaskTemplateRead],
    summary="重新启用任务模板(父母/管理端):清废弃标记并立即补生成",
)
async def activate_task_template(
    template_id: str, db: DBSession, user: GuildMasterOnly,
) -> ApiResponse[TaskTemplateRead]:
    template = await task_template_service.activate_template(
        db, family_id=user.family_id, template_id=template_id,
    )
    return ok(_to_read(template))


@router.post(
    "/{template_id}/regenerate",
    response_model=ApiResponse[dict],
    summary="再生成(父母/管理端):终结可用/进行中实例并尝试生成新实例",
)
async def regenerate_task_template(
    template_id: str, _body: TaskTemplateRegenerate, db: DBSession, user: GuildMasterOnly,
) -> ApiResponse[dict]:
    template, terminalized, fresh, action = await task_template_service.regenerate_template(
        db, family_id=user.family_id, template_id=template_id,
    )
    return ok({
        "template_id": template.id,
        "terminalized_instance_ids": [i.id for i in terminalized],
        # action: created=已生成新实例;kept=存在待审核实例(不终结不新增,见 §6A);
        # not_due/skipped_expired=当日无有效生成。new_instance 仅在 created 时非空。
        "action": action,
        "new_instance": {
            "id": fresh.id,
            "generated_for_date": str(fresh.generated_for_date),
            "status": fresh.status,
        } if (fresh is not None and action == "created") else None,
    })


@router.delete(
    "/{template_id}",
    response_model=ApiResponse[dict],
    summary="硬删任务模板(管理端):连同实例与触发规则一并删除",
)
async def delete_task_template(
    template_id: str, db: DBSession, user: GuildMasterOnly,
) -> ApiResponse[dict]:
    await _require_family_owner(db, user)
    await task_template_service.delete_template(
        db, family_id=user.family_id, template_id=template_id,
    )
    return ok({"ok": True})
