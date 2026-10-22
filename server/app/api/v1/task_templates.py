"""任务模板路由:模板级 CRUD / 生命周期 / 再生成 / 选模板生成(docs/12 块 A)。

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
    TaskGenerateRequest,
    TaskTemplateCreate,
    TaskTemplateDeprecate,
    TaskTemplateRead,
    TaskTemplateRegenerate,
    TaskTemplateUpdate,
    TaskTriggerRead,
)
from app.services import season_service, task_template_service

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


def _to_read(t, season_name: str | None = None) -> TaskTemplateRead:
    return TaskTemplateRead(
        id=t.id,
        family_id=t.family_id,
        season_id=t.season_id,
        # 来源赛季名(DEV-50):模板可跨赛季后,「来源赛季:{name}」弱提示靠它显示。
        season_name=season_name,
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
        chain_key=t.chain_key,
        chain_order=t.chain_order,
        chain_total=t.chain_total,
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
    names = await season_service.season_names(db, [t.season_id for t in items])
    return ok([_to_read(t, names.get(t.season_id)) for t in items])


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
    names = await season_service.season_names(db, [template.season_id])
    return ok(_to_read(template, names.get(template.season_id)))


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
    template_id, terminalized_ids, fresh, action = (
        await task_template_service.regenerate_template(
            db, family_id=user.family_id, template_id=template_id,
        )
    )
    return ok({
        "template_id": template_id,
        "terminalized_instance_ids": terminalized_ids,
        # action: created=已生成新实例;kept=存在待审核实例(不终结不新增,见 §6A);
        # exists=当日已有实例(含强生成撞当日已消费行);not_due/skipped_expired=
        # 当日无有效生成。new_instance 仅在 created 时非空。
        "action": action,
        "new_instance": {
            "id": fresh.id,
            "generated_for_date": str(fresh.generated_for_date),
            "status": fresh.status,
        } if (fresh is not None and action == "created") else None,
    })


@router.post(
    "/{template_id}/generate",
    response_model=ApiResponse[dict],
    summary="选模板生成任务(父母):指定目标日期,可覆盖难度/押金/经验值",
)
async def generate_task_instance(
    template_id: str, body: TaskGenerateRequest, db: DBSession, user: GuildMasterOnly,
) -> ApiResponse[dict]:
    """「选模板 → 生成 → 微调 → 落库」的生成入口(DEV-50)。

    与 `/{id}/regenerate` 的分界:`regenerate` 是"终结未消费实例 + 重建",
    确认文案与幂等语义都建立在"将终结 N 条"上;本入口是"为某一天生成一条",
    两者对用户的承诺不同,不合并。

    - `target_date` 缺省 = 今天;`< 今天` / `> 今天 + 30 天` → 422(一律按
      家庭本地时区 `today_bj()` 判定);
    - **豁免模板触发规则** —— 家长显式选模板生成,不该被日历规则挡住;
    - 实例赛季取**生成当时的激活赛季**,无激活赛季 → 409;
    - 三个数值字段未传 = 用模板值(快照),显式 `null` → 422;
    - 幂等:同一 (模板, 目标日) 已有实例则复用,不覆盖、不重建。

    出参回显实例的**生效值**,并带 `overrides_applied` —— 只有 `created` 时才
    真正写入覆盖值;其余动作复用既有实例,显式回传避免"传了覆盖值却被静默
    丢弃",前端据此把用户引导到 `PATCH /scn/task-instances/{id}`。
    """
    instance, action, overrides_applied = await task_template_service.generate_instance_for_template(
        db, family_id=user.family_id, template_id=template_id, payload=body,
    )
    if instance is None:
        # not_due(模板已停用)/ skipped_expired:没有产物,如实回报动作。
        return ok({
            "instance_id": None,
            "action": action,
            "generated_for_date": None,
            "status": None,
            "difficulty": None,
            "time_deposit": None,
            "xp_reward": None,
            "content_source": None,
            "season_name": None,
            "overrides_applied": overrides_applied,
        })
    names = await season_service.season_names(db, [instance.season_id])
    return ok({
        "instance_id": instance.id,
        "action": action,
        "generated_for_date": (
            str(instance.generated_for_date) if instance.generated_for_date else None
        ),
        "status": instance.status,
        "difficulty": instance.difficulty,
        "time_deposit": instance.time_deposit,
        "xp_reward": instance.xp_reward,
        "content_source": instance.content_source,
        "season_name": names.get(instance.season_id),
        "overrides_applied": overrides_applied,
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
