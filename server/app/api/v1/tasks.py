"""任务路由:模板 + 实例 CRUD 与状态机操作 + 任务证据(DEV-33 块 E)。"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.common.timeutil import today_bj
from app.deps import CurrentUser, DBSession, GuildMasterOnly
from app.models.enums import TaskStatus, TaskType, UserRole
from app.models.scn_task_proof import ScnTaskProof
from app.schemas.common import ApiResponse, PageQuery, PageResult, ok
from app.schemas.task import (
    TaskApproveRequest,
    TaskCreate,
    TaskDepositPreviewRequest,
    TaskDepositPreviewResponse,
    TaskParticipantRead,
    TaskProofRead,
    TaskRead,
    TaskRejectRequest,
    TaskSubmitRequest,
    TaskTuneRequest,
)
from app.services import (
    coin_service,
    coop_service,
    proof_service,
    season_service,
    task_service,
)
from app.services.upload_service import build_access_url

router = APIRouter(prefix="/scn/task-instances", tags=["scn-task-instances"])
templates_router = APIRouter(prefix="/scn/task-templates", tags=["scn-task-templates"])
proofs_router = APIRouter(prefix="/scn/task-proofs", tags=["scn-task-proofs"])


def _enum_value(value) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _template_value(t, name: str, default=None):
    template = getattr(t, "template", None)
    return getattr(template, name, default) if template is not None else default


def _proof_url(object_key: str) -> str | None:
    try:
        return build_access_url(object_key)
    except Exception:
        return None


def _proof_to_read(p: ScnTaskProof) -> TaskProofRead:
    return TaskProofRead(
        id=p.id,
        task_instance_id=p.task_instance_id,
        kind=p.kind,
        url=_proof_url(p.object_key),
        size=p.size,
        content_type=p.content_type,
        # 家长代交标注(docs/13 §4 裁决 Q3 展示侧要求):前端按
        # uploaded_by 是否为家长账号渲染"家长代交"角标,避免孩子侧混淆
        uploaded_by=p.uploaded_by,
        created_at=p.created_at,
    )


async def _load_proofs(db, task_ids: list[str]) -> dict[str, list[ScnTaskProof]]:
    """批量取各任务的未软删证据(避免列表接口 N+1)。"""
    if not task_ids:
        return {}
    rows = (
        await db.execute(
            select(ScnTaskProof)
            .where(
                ScnTaskProof.task_instance_id.in_(task_ids),
                ScnTaskProof.deleted_at.is_(None),
            )
            .order_by(ScnTaskProof.created_at, ScnTaskProof.id)
        )
    ).scalars().all()
    proofs: dict[str, list[ScnTaskProof]] = {}
    for row in rows:
        proofs.setdefault(row.task_instance_id, []).append(row)
    return proofs


def _to_read(
    t, proofs: list[ScnTaskProof] | None = None, season_name: str | None = None,
) -> TaskRead:
    # 块 E(证据)+ 块 F(参与者)语义合并:两条读取口径共存于同一 TaskRead。
    proofs = proofs or []
    proof_reads = [_proof_to_read(p) for p in proofs]
    # 过渡:proof_url = 首个证据的 URL;无证据行时回退到实例上的单值字段(存量数据)
    if proof_reads:
        proof_url = proof_reads[0].url
    elif t.proof_object_key:
        proof_url = _proof_url(t.proof_object_key)
    else:
        proof_url = None
    participants = [
        TaskParticipantRead(
            account_id=p.account_id,
            child_id=p.child_id,
            role=p.role,
            participant_status=p.participant_status or "JOINED",
            confirmed_at=p.confirmed_at,
            deposit_share=p.deposit_share,
            xp_awarded=p.xp_awarded,
        )
        for p in getattr(t, "participants", [])
    ]
    return TaskRead(
        id=t.id,
        family_id=t.family_id,
        season_id=t.season_id,
        season_name=season_name,
        template_id=t.template_id,
        creator_account_id=t.creator_account_id,
        target_child_id=t.target_child_id,
        assignee_child_id=t.assignee_child_id,
        category=_template_value(t, "category"),
        title=t.title,
        description=t.description,
        lore_snippet=t.lore_snippet,
        xp_reward=t.xp_reward,
        type=_template_value(t, "type", TaskType.DAILY),
        status=t.status,
        deadline=t.deadline,
        expire_at=t.expire_at,
        generated_for_date=t.generated_for_date,
        required_start_time=_template_value(t, "required_start_time"),
        # DEV-50:难度**快照**,直读实例,不再从模板穿读 —— 否则家长微调的
        # 星级读不回来。存量行由迁移回填;NULL = 生成时模板未评星。
        difficulty=t.difficulty,
        estimated_minutes=_template_value(t, "estimated_minutes"),
        proof_url=proof_url,
        proofs=proof_reads,
        rating=t.rating,
        review_comment=t.review_comment,
        xp_awarded=t.xp_awarded,
        coin_delta=t.coin_delta,
        abandon_count_at_submit=t.abandon_count_at_submit,
        started_at=t.started_at,
        submitted_at=t.submitted_at,
        completed_at=t.completed_at,
        reminder_message=_template_value(t, "reminder_message"),
        reminder_minutes_before=_template_value(t, "reminder_minutes_before", 15),
        time_deposit=t.time_deposit,
        chain_index=t.chain_index,
        chain_total=t.chain_total,
        content_source=t.content_source,
        participants=participants,
        created_at=t.created_at,
        updated_at=t.updated_at,
        creator_id=t.creator_account_id,
        target_user_id=t.target_child_id,
        assignee_id=t.assignee_child_id,
    )


async def _to_read_with_proofs(db, t) -> TaskRead:
    names = await season_service.season_names(db, [t.season_id])
    return _to_read(
        t,
        await proof_service.list_proofs(db, task_instance_id=t.id),
        names.get(t.season_id),
    )


@router.get("", response_model=ApiResponse[PageResult[TaskRead]], summary="任务实例列表")
async def list_tasks(
    db: DBSession, user: CurrentUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    season_id: str | None = Query(default=None),
    status: TaskStatus | None = Query(default=None),
    template_id: str | None = Query(default=None),
    assignee_child_id: str | None = Query(default=None),
    assignee_id: str | None = Query(default=None),
    generated_for_date_lte: date | None = Query(
        default=None,
        description="只返回该逻辑日及以前的实例(管理端可选筛选;孩子端由服务端强制取今天)",
    ),
) -> ApiResponse[PageResult[TaskRead]]:
    """任务实例列表。

    **DEV-50 可见性:孩子端由服务端强制过滤,不信客户端参数。**
    "已排期到明天"的实例在到期前不该出现在孩子的任务板上 —— 这是权限边界,
    前端过滤可被绕过;而且前端"拉 N 条再筛"会被未来实例挤占窗口、把当天任务
    挤掉。管理端默认看全量(家长要能看见自己排期的任务),另给可选
    `generated_for_date_lte` 做显式筛选。
    """
    query = PageQuery(page=page, page_size=page_size)
    is_child = _enum_value(user.role) == UserRole.ADVENTURER.value
    visible_until = today_bj() if is_child else generated_for_date_lte
    items, total = await task_service.list_tasks(
        db, family_id=user.family_id,
        season_id=season_id, status=status, assignee_id=assignee_child_id or assignee_id,
        template_id=template_id,
        generated_for_date_lte=visible_until,
        offset=query.offset, limit=query.page_size,
    )
    proofs_map = await _load_proofs(db, [t.id for t in items])
    names_map = await season_service.season_names(db, [t.season_id for t in items])
    return ok(PageResult(
        items=[_to_read(t, proofs_map.get(t.id), names_map.get(t.season_id)) for t in items],
        total=total,
        page=query.page,
        page_size=query.page_size,
    ))


@router.get("/{task_id}", response_model=ApiResponse[TaskRead], summary="任务实例详情")
async def get_task(task_id: str, db: DBSession, user: CurrentUser) -> ApiResponse[TaskRead]:
    """任务实例详情。

    **DEV-50 可见性(审查 🟡3):详情与列表同一条边界。** 列表那半边是服务端按
    角色强制的,详情若只靠"id 不可猜"就是同一件事只做了一半。虽然当前没有可
    证实的外泄路径(id 不可猜、通知不带实例 id),但既然另半边是按权限边界做
    的,就没有理由留着不对称:孩子读到"已排期到未来"的实例 → 404(不泄露它
    存在,与跨家庭一律 404 同口径)。
    """
    t = await task_service.get_task(db, task_id)
    if t.family_id != user.family_id:
        from app.common.exceptions import PermissionDeniedError
        raise PermissionDeniedError("只能查看自己家庭的任务")
    if _enum_value(user.role) == UserRole.ADVENTURER.value:
        scheduled = t.generated_for_date is not None and t.generated_for_date > today_bj()
        if scheduled:
            from app.common.exceptions import NotFoundError
            raise NotFoundError(f"任务 {task_id} 不存在")
    return ok(await _to_read_with_proofs(db, t))


@router.post(
    "",
    response_model=ApiResponse[TaskRead],
    summary="创建任务实例(父母):ephemeral=true 只建实例不落模板;否则建模板+初始实例(deprecated)",
)
async def create_task(
    body: TaskCreate, db: DBSession, user: GuildMasterOnly,
) -> ApiResponse[TaskRead]:
    """按 `ephemeral` 分流(DEV-59):

    - **`ephemeral=true`(临时任务,新入口)**:只建实例、**不落模板**——任务板
      「创建新任务」未选模板分支走这条。返回体 `template_id` 恒为 `null`。
      不进模板库、不参与实例池(无触发规则/无链式/不跨天顺延)。
    - `ephemeral=false`(缺省,【deprecated,DEV-50】):一次成型建模板 + 建一条
      实例。已由「选模板 → 生成」取代(`POST /scn/task-templates/{id}/generate`),
      不支持目标日期与逐实例微调,且实例不写 `generated_for_date`。保留仅为兼容
      旧客户端,新前端请勿使用。
    """
    if body.ephemeral:
        t = await task_service.create_ephemeral_task(
            db, family_id=user.family_id, creator_id=user.id, payload=body,
        )
        return ok(await _to_read_with_proofs(db, t))
    data = body.model_dump()
    t = await task_service.create_task(
        db, family_id=user.family_id, creator_id=user.id, **data,
    )
    return ok(_to_read(t))


@router.patch(
    "/{task_id}",
    response_model=ApiResponse[TaskRead],
    summary="微调任务实例(父母):难度 / 押金 / 经验值",
)
async def tune_task(
    task_id: str, body: TaskTuneRequest, db: DBSession, user: GuildMasterOnly,
) -> ApiResponse[TaskRead]:
    """逐实例微调(DEV-50)。

    三个字段都是**快照**,语义同构:`exclude_unset` —— 未提供 = 保持不变;
    显式 `null` → 422(「恢复模板值」由前端取模板当前值后作为数字提交,
    因为 `xp_reward` / `time_deposit` 是 `NOT NULL`、根本没有 NULL 态,写 null
    既是约束违例、也会把"一次性填入"伪装成"持续跟随模板")。

    实例的 `season_id` 不可改(任务不跨赛季),故不在契约中。
    仅 `AVAILABLE`(未接取)可调:接取后押金已扣,再改会让退款/超时结算口径漂移。
    """
    t = await task_service.tune_task(
        db, task_id=task_id, family_id=user.family_id, payload=body,
    )
    return ok(await _to_read_with_proofs(db, t))


# 注:DEV-36 块 F 的"只建模板不投放实例"入口(POST /scn/task-templates,
# task_service.create_task_template)已并入块 A 的 task_templates.py 路由:
# 同 URL 只保留一个 handler(链校验已接线到 task_template_service.create_template,
# CHAIN 后续步骤模板无默认触发规则,创建后不会长出实例),避免路由遮蔽。

@router.delete("/{task_id}", response_model=ApiResponse[dict], summary="删除任务实例(父母)")
async def delete_task(task_id: str, db: DBSession, user: GuildMasterOnly) -> ApiResponse[dict]:
    await task_service.delete_task(db, task_id=task_id, family_id=user.family_id)
    return ok({"ok": True})


@router.post("/{task_id}/start", response_model=ApiResponse[TaskRead], summary="孩子接取任务")
async def start_task(
    task_id: str, db: DBSession, user: CurrentUser,
) -> ApiResponse[TaskRead]:
    t = await task_service.start_task(db, task_id=task_id, user=user)
    return ok(_to_read(t))


@router.post("/{task_id}/join", response_model=ApiResponse[TaskRead], summary="加入 COOP 协作任务(孩子=均摊押金 / 家长=亲子参与)")
async def join_task(
    task_id: str, db: DBSession, user: CurrentUser,
) -> ApiResponse[TaskRead]:
    t = await coop_service.join_task(db, task_id=task_id, user=user)
    return ok(await _to_read_with_proofs(db, t))


@router.post("/{task_id}/submit", response_model=ApiResponse[TaskRead], summary="孩子提交(多证据)")
async def submit_task(
    task_id: str, body: TaskSubmitRequest, db: DBSession, user: CurrentUser,
) -> ApiResponse[TaskRead]:
    t = await task_service.submit_task(
        db, task_id=task_id, user=user,
        proof_object_keys=body.proof_object_keys,
        proof_object_key=body.proof_object_key,
    )
    return ok(await _to_read_with_proofs(db, t))


@router.post("/{task_id}/approve", response_model=ApiResponse[TaskRead], summary="父母审核通过(整单/逐人/部分通过判退)")
async def approve_task(
    task_id: str, body: TaskApproveRequest, db: DBSession, user: GuildMasterOnly,
) -> ApiResponse[TaskRead]:
    t, _assignee, _info = await task_service.approve_task(
        db, task_id=task_id, family_id=user.family_id, rating=body.rating, comment=body.comment,
        child_id=body.child_id, participant_id=body.participant_id,
        settle_partial=body.settle_partial,
    )
    return ok(await _to_read_with_proofs(db, t))


@router.post("/{task_id}/reject", response_model=ApiResponse[TaskRead], summary="父母审核驳回(打回重做)")
async def reject_task(
    task_id: str, body: TaskRejectRequest, db: DBSession, user: GuildMasterOnly,
) -> ApiResponse[TaskRead]:
    t = await task_service.reject_task(
        db, task_id=task_id, family_id=user.family_id, comment=body.comment,
    )
    return ok(await _to_read_with_proofs(db, t))


@router.post("/{task_id}/abandon", response_model=ApiResponse[TaskRead], summary="孩子放弃")
async def abandon_task(
    task_id: str, db: DBSession, user: CurrentUser,
) -> ApiResponse[TaskRead]:
    t, _u, _refund = await task_service.abandon_task(db, task_id=task_id, user=user)
    return ok(await _to_read_with_proofs(db, t))


@router.post("/{task_id}/leave", response_model=ApiResponse[TaskRead], summary="退出 COOP 协作任务(参与者个人退出,主接取人请走 abandon)")
async def leave_task(
    task_id: str, db: DBSession, user: CurrentUser,
) -> ApiResponse[TaskRead]:
    """docs/13 定稿版 §4:参与者退出,押金按当日放弃阶梯退并递增放弃计数。"""
    t = await task_service.leave_task(db, task_id=task_id, user=user)
    return ok(await _to_read_with_proofs(db, t))


@router.get(
    "/{task_id}/proofs",
    response_model=ApiResponse[list[TaskProofRead]],
    summary="任务的证据列表(未软删,按提交顺序)",
)
async def list_task_proofs(
    task_id: str, db: DBSession, user: CurrentUser,
) -> ApiResponse[list[TaskProofRead]]:
    """DEV-33 块 E(docs/07 A7.2):家长审核端逐张/逐段查看的证据来源。"""
    task = await task_service.get_task(db, task_id)
    if task.family_id != user.family_id:
        from app.common.exceptions import PermissionDeniedError
        raise PermissionDeniedError("只能查看自己家庭的任务证据")
    proofs = await proof_service.list_proofs(db, task_instance_id=task_id)
    return ok([_proof_to_read(p) for p in proofs])


@proofs_router.get(
    "/{proof_id}",
    response_model=ApiResponse[TaskProofRead],
    summary="单条任务证据",
)
async def get_proof(proof_id: str, db: DBSession, user: CurrentUser) -> ApiResponse[TaskProofRead]:
    proof = await proof_service.get_proof(db, proof_id)
    if proof.family_id != user.family_id:
        from app.common.exceptions import PermissionDeniedError
        raise PermissionDeniedError("只能查看自己家庭的任务证据")
    return ok(_proof_to_read(proof))


@proofs_router.delete(
    "/{proof_id}",
    response_model=ApiResponse[dict],
    summary="软删一条任务证据(deleted_at 置位)",
)
async def delete_proof(
    proof_id: str, db: DBSession, user: CurrentUser,
) -> ApiResponse[dict]:
    proof = await proof_service.get_proof(db, proof_id)
    await proof_service.soft_delete_proof(db, proof=proof, actor=user)
    return ok({"ok": True})


@templates_router.post(
    "/preview-deposit",
    response_model=ApiResponse[TaskDepositPreviewResponse],
    summary="预览押金(父母创建表单实时显示;难度不影响押金)",
)
async def preview_deposit(
    body: TaskDepositPreviewRequest, db: DBSession, user: GuildMasterOnly,
) -> ApiResponse[TaskDepositPreviewResponse]:
    # DEV-50:配额按**星期几**不同(ScnTimeConfig.exceptions),为未来日期生成时
    # 必须按目标日的配额算封顶,否则会拿工作日的上限去卡周末。
    day = body.for_date or coin_service.today_bj()
    allowance = await coin_service.compute_daily_allowance(db, user.family_id, day)
    time_deposit, capped = coin_service.compute_deposit_detail(
        task_type=body.type,
        estimated_minutes=body.estimated_minutes,
        explicit_deposit=body.time_deposit,
        daily_allowance=allowance,
    )
    return ok(TaskDepositPreviewResponse(
        time_deposit=time_deposit,
        daily_allowance=allowance,
        # 仅在解析值真正被配额封顶截断时置位;恰好等于上限不算(封顶态是前端视觉提示依据)
        capped_by_allowance=capped,
    ))
