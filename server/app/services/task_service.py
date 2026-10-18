"""任务服务:模板/实例 + 状态机 + 押金/退款 + 审批。"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.common.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from app.common.timeutil import today_bj, utcnow
from app.config import settings
from app.models.enums import (
    CoinTransactionType,
    ContentMode,
    NotificationChannel,
    NotificationStatus,
    NotificationType,
    TaskParticipantRole,
    TaskParticipantStatus,
    TaskStatus,
    TaskType,
    UploadPurpose,
    UserRole,
)
from app.models.scn_notification import ScnNotification
from app.models.scn_season import ScnSeason
from app.models.scn_task_instance import ScnTaskInstance
from app.models.scn_task_participant import ScnTaskParticipant
from app.models.scn_task_proof import ScnTaskProof
from app.models.scn_task_template import ScnTaskTemplate
from app.models.scn_task_template_library import ScnTaskTemplateLibrary
from app.models.sys_account import SysAccount
from app.models.sys_child import SysChild
from app.models.sys_upload import SysUpload
from app.services import (
    chain_service,
    coin_service,
    coop_service,
    privilege_service,
    proof_service,
    xp_service,
)

# 驳回时若原 expire_at 已过(孩子在截止前提交,但家长审核拖到截止后才驳回),
# 补一个重新提交窗口,避免下一轮过期批处理(expire_overdue_tasks)把它当成
# "未在截止前处理"直接判 EXPIRED,吞掉"驳回后孩子可修改重提交"的流程。
REJECT_RESUBMIT_GRACE = timedelta(hours=24)


def _enum_value(value) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _deposit_of(task: ScnTaskInstance) -> int:
    """任务押金总额。`or` 会把家长刻意设的 0 押金变成 10,故用显式 None 判断
    (MR #10 审查建议 3)。"""
    return task.time_deposit if task.time_deposit is not None else 10


async def get_task_for_update(db: AsyncSession, task_id: str) -> ScnTaskInstance:
    """行锁取任务实例(MR #10 审查 🔴 修复)。

    COOP 的押金重摊/结算都是读-改-写,并发下会破坏"已收之和 == 总额"的
    金额守恒。settle 路径(approve/abandon/expire)先进本函数拿实例行锁,
    与 coop_service.join_task 的锁互斥(同一行 FOR UPDATE);
    顺带消除并发双审批(第二个事务等锁后读到 COMPLETED,409)。
    先例: DEV-20 `family_service._lock_invite_or_raise`。
    """
    t = (await db.execute(
        select(ScnTaskInstance)
        .where(ScnTaskInstance.id == task_id)
        .with_for_update()
        .options(selectinload(ScnTaskInstance.template))
    )).scalar_one_or_none()
    if not t:
        raise NotFoundError(f"任务 {task_id} 不存在")
    return t


async def _ensure_child(db: AsyncSession, *, family_id: str, child_id: str) -> SysChild:
    child = await db.get(SysChild, child_id)
    if child is None:
        child = (
            await db.execute(select(SysChild).where(SysChild.account_id == child_id))
        ).scalar_one_or_none()
    if not child:
        raise NotFoundError(f"孩子 {child_id} 不存在")
    if child.family_id != family_id:
        raise PermissionDeniedError("只能操作自己家庭成员的任务")
    return child


async def _account_child(db: AsyncSession, user: SysAccount) -> SysChild:
    if _enum_value(user.role) != UserRole.ADVENTURER.value:
        raise PermissionDeniedError("只有 ADVENTURER 可以操作该任务")
    return await _ensure_child(db, family_id=user.family_id, child_id=user.id)


async def _ensure_task_refs(
    db: AsyncSession, *, family_id: str, season_id: str, target_child_id: str | None
) -> None:
    season = await db.get(ScnSeason, season_id)
    if not season:
        raise NotFoundError(f"赛季 {season_id} 不存在")
    if season.family_id != family_id:
        raise PermissionDeniedError("只能在自己家庭的赛季中创建任务")
    if target_child_id is not None:
        await _ensure_child(db, family_id=family_id, child_id=target_child_id)


async def create_task_template(
    db: AsyncSession, *, family_id: str, creator_id: str, **kwargs
) -> ScnTaskTemplate:
    """只建模板、不投放实例(DEV-36 块 F)。

    CHAIN 链的第 2..N 步用本入口创建:链式任务的实例由"链首投放 +
    逐步解锁"生成,后续步骤模板不该在创建时就长出实例(详见 chain_service)。
    """
    season_id = kwargs["season_id"]
    await _ensure_task_refs(
        db,
        family_id=family_id,
        season_id=season_id,
        target_child_id=kwargs.get("target_child_id"),
    )
    task_type = kwargs.get("type") or TaskType.DAILY
    await chain_service.validate_chain_template(
        db,
        family_id=family_id,
        task_type=task_type,
        chain_key=kwargs.get("chain_key"),
        chain_order=kwargs.get("chain_order", 1),
        chain_total=kwargs.get("chain_total", 1),
    )

    template = ScnTaskTemplate(
        family_id=family_id,
        season_id=season_id,
        creator_account_id=creator_id,
        library_id=kwargs.get("library_id"),
        target_child_id=kwargs.get("target_child_id"),
        category=kwargs.get("category"),
        title=kwargs["title"],
        description=kwargs.get("description", ""),
        lore_snippet=kwargs.get("lore_snippet"),
        xp_reward=kwargs.get("xp_reward", 50),
        type=task_type,
        required_start_time=kwargs.get("required_start_time"),
        reminder_message=kwargs.get("reminder_message"),
        reminder_minutes_before=kwargs.get("reminder_minutes_before", 15),
        time_deposit=kwargs.get("time_deposit", 10),
        is_active=kwargs.get("is_active", True),
        chain_key=kwargs.get("chain_key"),
        chain_order=kwargs.get("chain_order", 1),
        chain_total=kwargs.get("chain_total", 1),
        estimated_minutes=kwargs.get("estimated_minutes"),
        difficulty=kwargs.get("difficulty", 1),
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return template


async def create_task(db: AsyncSession, *, family_id: str, creator_id: str, **kwargs) -> ScnTaskInstance:
    """兼容旧 create_task API:同时创建模板与一条初始实例。

    押金在创建时即由 `coin_service.resolve_deposit` 解析落库(显式值优先,
    否则按预计耗时 × 类型默认值),此后各环节直接用 `time_deposit` 字段,
    不再有 `or 10` 之类的写死兜底。
    """
    target_child_id = kwargs.pop("target_child_id", None) or kwargs.pop("target_user_id", None)
    season_id = kwargs["season_id"]
    await _ensure_task_refs(
        db,
        family_id=family_id,
        season_id=season_id,
        target_child_id=target_child_id,
    )
    task_type = kwargs.get("type") or TaskType.DAILY
    chain_order = kwargs.get("chain_order", 1)
    if task_type == TaskType.CHAIN and chain_order != 1:
        raise ValidationError(
            "CHAIN 任务只投放链首步(chain_order=1);"
            "后续步骤模板请走 POST /scn/task-templates,由链逐步解锁生成实例"
        )
    await chain_service.validate_chain_template(
        db,
        family_id=family_id,
        task_type=task_type,
        chain_key=kwargs.get("chain_key"),
        chain_order=chain_order,
        chain_total=kwargs.get("chain_total", 1),
    )

    library_id = kwargs.get("library_id")
    explicit_deposit = kwargs.get("time_deposit")
    if explicit_deposit is None and library_id:
        # 模板库套用:用 suggested_time_deposit 播种(显式值,仍受类型范围/配额封顶约束)
        library = await db.get(ScnTaskTemplateLibrary, library_id)
        if library is not None and library.family_id not in (None, family_id):
            raise PermissionDeniedError("只能套用平台或自己家庭的模板库")
        if library is not None:
            explicit_deposit = library.suggested_time_deposit

    task_type = kwargs.get("type") or TaskType.DAILY
    estimated_minutes = kwargs.get("estimated_minutes")
    deposit = await coin_service.resolve_deposit(
        db,
        family_id=family_id,
        task_type=task_type,
        estimated_minutes=estimated_minutes,
        explicit_deposit=explicit_deposit,
        day=today_bj(),
    )

    template = ScnTaskTemplate(
        family_id=family_id,
        season_id=season_id,
        creator_account_id=creator_id,
        library_id=library_id,
        target_child_id=target_child_id,
        category=kwargs.get("category"),
        title=kwargs["title"],
        description=kwargs.get("description", ""),
        lore_snippet=kwargs.get("lore_snippet"),
        xp_reward=kwargs.get("xp_reward", 50),
        type=task_type,
        required_start_time=kwargs.get("required_start_time"),
        reminder_message=kwargs.get("reminder_message"),
        reminder_minutes_before=kwargs.get("reminder_minutes_before", 15),
        difficulty=kwargs.get("difficulty") or 2,
        estimated_minutes=estimated_minutes,
        time_deposit=deposit,
        is_active=True,
        chain_key=kwargs.get("chain_key"),
        chain_order=chain_order,
        chain_total=kwargs.get("chain_total", 1),
        # docs/15:内容字段落到模板(叙事由生成器批量作业产出,本路径不调 LLM)
        content_mode=kwargs.get("content_mode") or ContentMode.STATIC,
        content_brief=kwargs.get("content_brief"),
    )
    db.add(template)
    await db.flush()

    task = ScnTaskInstance(
        family_id=family_id,
        season_id=season_id,
        template_id=template.id,
        creator_account_id=creator_id,
        target_child_id=target_child_id,
        title=template.title,
        description=template.description,
        lore_snippet=template.lore_snippet,
        xp_reward=template.xp_reward,
        status=TaskStatus.AVAILABLE,
        deadline=kwargs.get("deadline"),
        expire_at=kwargs.get("expire_at") or kwargs.get("deadline"),
        time_deposit=template.time_deposit,
        chain_index=template.chain_order if template.chain_key else None,
        chain_total=template.chain_total if template.chain_key else None,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


async def get_task(db: AsyncSession, task_id: str) -> ScnTaskInstance:
    t = (await db.execute(
        select(ScnTaskInstance)
        .where(ScnTaskInstance.id == task_id)
        .options(selectinload(ScnTaskInstance.template))
    )).scalar_one_or_none()
    if not t:
        raise NotFoundError(f"任务 {task_id} 不存在")
    return t


async def list_tasks(
    db: AsyncSession, *, family_id: str, season_id: str | None = None,
    status: TaskStatus | None = None, assignee_id: str | None = None,
    template_id: str | None = None,
    offset: int = 0, limit: int | None = None,
) -> tuple[list[ScnTaskInstance], int]:
    stmt = select(ScnTaskInstance).where(ScnTaskInstance.family_id == family_id)
    if season_id is not None:
        stmt = stmt.where(ScnTaskInstance.season_id == season_id)
    if status is not None:
        stmt = stmt.where(ScnTaskInstance.status == status)
    if template_id is not None:
        # 模板维度筛实例(DEV-35):详情抽屉/重新生成确认弹窗数未消费实例用。
        stmt = stmt.where(ScnTaskInstance.template_id == template_id)
    if assignee_id is not None:
        child = await _ensure_child(db, family_id=family_id, child_id=assignee_id)
        stmt = stmt.where(ScnTaskInstance.assignee_child_id == child.id)

    total = int((await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one())

    stmt = stmt.options(selectinload(ScnTaskInstance.template)).order_by(ScnTaskInstance.id.desc()).offset(offset)
    if limit is not None:
        stmt = stmt.limit(limit)
    items = list((await db.execute(stmt)).scalars().all())
    return items, total


async def start_task(
    db: AsyncSession, *, task_id: str, user: SysAccount,
) -> ScnTaskInstance:
    """孩子接取任务:扣押金、状态切 IN_PROGRESS。"""
    child = await _account_child(db, user)
    task = await get_task(db, task_id)
    if task.family_id != user.family_id:
        raise PermissionDeniedError("只能操作自己家庭的任务")
    if task.status != TaskStatus.AVAILABLE:
        raise ConflictError(f"任务当前状态为 {_enum_value(task.status)},不可接取")
    if task.target_child_id and task.target_child_id != child.id:
        raise PermissionDeniedError("该任务指定了其他接取人")

    if coop_service.is_coop(task):
        # COOP:主接取人先按 n=1 承担全额押金并登记 OWNER 参与者;
        # 后续孩子 join 时会重新均摊并向他退差额(coop_service.join_task)。
        deposit = coop_service.per_participant_shares(_deposit_of(task), 1)[0]
    else:
        deposit = coin_service.calculate_deposit_fee(_deposit_of(task))
    if not coin_service.has_sufficient_coins(child, deposit):
        raise ValidationError(
            f"时间币不足,需要 {deposit},当前 {child.time_coin_balance}"
        )

    child.time_coin_balance -= deposit
    await coin_service.record_transaction(
        db,
        child=child,
        type=CoinTransactionType.TASK_DEPOSIT,
        amount=-deposit,
        task_instance_id=task.id,
        note="接取任务扣除押金",
    )
    task.status = TaskStatus.IN_PROGRESS
    task.assignee_child_id = child.id
    task.started_at = utcnow()

    if coop_service.is_coop(task):
        task.participants.append(ScnTaskParticipant(
            task_instance_id=task.id,
            account_id=child.account_id,
            child_id=child.id,
            role=TaskParticipantRole.OWNER,
            confirmed_at=utcnow(),
            deposit_share=deposit,
        ))

    await db.commit()
    await db.refresh(task)
    return task


async def submit_task(
    db: AsyncSession, *, task_id: str, user: SysAccount,
    proof_object_keys: list[str] | None = None,
    proof_object_key: str | None = None,
) -> ScnTaskInstance:
    """参与者提交(docs/13 定稿版 §4,DEV-40 扩展:任意参与者可为自己提交)。

    多证据(DEV-33 块 E):`proof_object_keys` 是主入口;`proof_object_key`
    为旧客户端过渡字段(等价单元素列表)。逐个校验(存在、属于当前用户、
    purpose=task_proof、未被其他任务占用、kind 可推导)后整体落库:

    - **COOP**:提交者必须是已确认参与者(孩子或家长,裁决 Q3:家长交付同样
      走 proof);proof 行 `uploaded_by` = 提交者;收缩/复活只作用于**本人**
      名下的证据行(他人已交的证据不动);本人 `participant_status → SUBMITTED`;
      全员已交 → 实例 `PENDING_REVIEW`,否则站内通知主接取人与未交者
      (`COOP_PARTIAL_SUBMITTED`)。
    - **单人**:现行为不变(接取人提交 → PENDING_REVIEW)。

    不在本次集合中的本人旧证据 → 软删(提交即"当前所选集合",驳回重交
    时旧图自动退出审核视图,也规避 object_key 唯一约束);集合中已存在
    (含软删)的本人证据 → 复活,并按本次提交序位重排 created_at(保证
    读取顺序恒等于本次提交顺序,DEV-42);其余 → 新建 scn_task_proof 行,
    并把 sys_upload.task_instance_id 回填绑定。
    """
    keys = [k for k in (proof_object_keys or []) if k]
    if not keys and proof_object_key:
        keys = [proof_object_key]
    if not keys:
        raise ValidationError("至少提交一个证明文件")
    if len(set(keys)) != len(keys):
        raise ValidationError("提交的证明文件存在重复")
    max_files = settings.upload.max_proof_files
    if len(keys) > max_files:
        raise ValidationError(f"证明文件数量超过上限 {max_files}")

    role_value = _enum_value(user.role)
    # 行锁:COOP 分支承担实例状态迁移(全员已交 → PENDING_REVIEW),是读-判-写路径;
    # 并发末两次提交不加锁会各自读到对方仍 JOINED 的旧快照,all_delivered 双双为 False,
    # 全员 SUBMITTED 却停在 IN_PROGRESS(docs/13 §3 不变量被静默打破)。
    # 与 join 重摊(MR #10 审查 🔴)/settle 路径同一把实例行锁互斥(DEV-40 审查 🟡)。
    task = await get_task_for_update(db, task_id)
    if task.family_id != user.family_id:
        raise PermissionDeniedError("只能操作自己家庭的任务")

    coop = coop_service.is_coop(task)
    participant: ScnTaskParticipant | None = None
    child: SysChild | None = None
    if coop and role_value == UserRole.GUILD_MASTER.value:
        # 亲子协作:家长参与者为自己交卷(无 child_id,按账号定位)
        participant = coop_service.find_participant(task, account_id=user.id)
        if participant is None or participant.confirmed_at is None:
            raise PermissionDeniedError("你不是该协作任务的参与者")
    else:
        child = await _account_child(db, user)
        if coop:
            participant = coop_service.find_participant(task, child_id=child.id)
            if participant is None or participant.confirmed_at is None:
                raise PermissionDeniedError("你不是该协作任务的参与者")
        elif task.assignee_child_id != child.id:
            raise PermissionDeniedError("你不是该任务的接取人")
    if task.status != TaskStatus.IN_PROGRESS:
        raise ConflictError(f"当前状态 {_enum_value(task.status)},无法提交")

    # 逐个校验(先全部校验再落库,任何一个不合法整单拒绝,不留半提交状态):
    # 存在 + 上传者是当前用户 + purpose=task_proof(DEV-20 归属校验,防 local
    # 模式下用任意字符串引用/探测他人对象)+ kind 可由 content_type 推导。
    uploads = (
        await db.execute(select(SysUpload).where(SysUpload.object_key.in_(keys)))
    ).scalars().all()
    uploads_by_key = {u.object_key: u for u in uploads}
    for key in keys:
        upload = uploads_by_key.get(key)
        if (
            upload is None
            or upload.uploader_account_id != user.id
            or upload.purpose != UploadPurpose.TASK_PROOF
        ):
            raise ValidationError(f"证明文件 {key} 不存在、不是任务凭证或不属于当前用户")
        if proof_service.proof_kind_for_content_type(upload.content_type) is None:
            raise ValidationError(f"证明文件 {key} 的类型不支持: {upload.content_type}")
        # 任务关联(DEV-30):未绑定的凭证回填;已绑定其他任务的凭证拒绝复用。
        if upload.task_instance_id is not None and upload.task_instance_id != task.id:
            raise ValidationError(f"证明文件 {key} 已关联其他任务,请重新上传")

    # 证据占用校验:object_key 在 scn_task_proof 上全局唯一(含软删行),
    # 已属于其他任务的 key 一律拒绝,即使是软删状态也不能复活成新任务的证据。
    existing_proof_rows = (
        await db.execute(select(ScnTaskProof).where(ScnTaskProof.object_key.in_(keys)))
    ).scalars().all()
    proofs_by_key = {row.object_key: row for row in existing_proof_rows}
    for key, row in proofs_by_key.items():
        if row.task_instance_id != task.id:
            raise ValidationError(f"证明文件 {key} 已被其他任务占用,请重新上传")

    key_set = set(keys)
    # 1) 收缩:本人在本任务不在本次集合中的证据软删(提交即"当前所选集合");
    #    集合内的复活/复用在下面第 2 步按本次提交序位一并重排。
    #    COOP 下只动本人名下(uploaded_by=当前提交者)的行——队友已交的证据不属于
    #    本次提交集合,不能被顺带软删(docs/13 §4 各参与者各自提交)。
    task_proof_rows = (
        await db.execute(
            select(ScnTaskProof).where(
                ScnTaskProof.task_instance_id == task.id,
                ScnTaskProof.uploaded_by == user.id,
            )
        )
    ).scalars().all()
    for row in task_proof_rows:
        if row.object_key not in key_set:
            row.deleted_at = utcnow()
    # 2) 台账回填绑定 + 复活/新建证据行。
    #    created_at 按提交顺序显式加微秒偏移:同一事务里 server_default now()
    #    会给出相同时间戳,排序退化为随机 UUID;显式错开才能保证读取端
    #    (ORDER BY created_at, id)稳定还原提交顺序。
    #    复活/复用行(DEV-42)同样重排 created_at:复活行若保留上次提交的
    #    旧时间戳,会排在本次新建行之前,导致 proofs[0](=proof_url)与
    #    keys[0](=task.proof_object_key)不一致。created_at 在本表即"提交
    #    序位",每次提交整体重写一遍,读取顺序恒等于本次提交顺序。
    now = utcnow()
    for idx, key in enumerate(keys):
        upload = uploads_by_key[key]
        if upload.task_instance_id is None:
            upload.task_instance_id = task.id
        ordered_created_at = now + timedelta(microseconds=idx)
        existing = proofs_by_key.get(key)
        if existing is not None:
            existing.deleted_at = None  # 复用/复活本任务已有的证据行
            existing.created_at = ordered_created_at
        else:
            db.add(ScnTaskProof(
                family_id=task.family_id,
                task_instance_id=task.id,
                kind=proof_service.proof_kind_for_content_type(upload.content_type),
                object_key=key,
                size=upload.size,
                content_type=upload.content_type,
                uploaded_by=user.id,
                created_at=ordered_created_at,
            ))

    task.proof_object_key = keys[0]  # 过渡字段:首个证据,读取以 scn_task_proof 为准
    task.submitted_at = now
    if child is not None:
        task.abandon_count_at_submit = child.daily_abandon_count

    if coop:
        participant.participant_status = TaskParticipantStatus.SUBMITTED.value
        if coop_service.all_delivered(task):
            task.status = TaskStatus.PENDING_REVIEW
        else:
            # 部分交卷:提醒主接取人与未交者(docs/13 §6)
            _notify_coop_participants(
                db, task,
                type_=NotificationType.COOP_PARTIAL_SUBMITTED,
                recipient_participants=[
                    p for p in task.participants
                    if p.account_id != user.id
                    and coop_service.participant_status_of(p) == TaskParticipantStatus.JOINED
                ] + [
                    p for p in task.participants
                    if p.role == TaskParticipantRole.OWNER and p.account_id != user.id
                ],
                title="协作任务有人交卷",
                body=f"任务「{task.title}」有参与者已提交,等待其余参与者完成。",
                payload={
                    "task_instance_id": task.id,
                    "submitted_account_id": user.id,
                    "pending_count": len(coop_service.undelivered_participants(task)),
                },
            )
    else:
        task.status = TaskStatus.PENDING_REVIEW
    await db.commit()
    await db.refresh(task)
    return task


def _notify_coop_participants(
    db: AsyncSession, task: ScnTaskInstance, *, type_: NotificationType,
    recipient_participants: list[ScnTaskParticipant],
    title: str, body: str, payload: dict | None = None,
) -> None:
    """COOP 参与者站内通知(INAPP 直写即达,与 _notify_task_expired 同口径)。"""
    for account_id in dict.fromkeys(p.account_id for p in recipient_participants):
        if not account_id:
            continue
        db.add(ScnNotification(
            family_id=task.family_id,
            recipient_account_id=account_id,
            channel=NotificationChannel.INAPP,
            type=type_,
            title=title,
            body=body,
            payload=payload or {},
            status=NotificationStatus.SENT,
            sent_at=utcnow(),
        ))


async def _settle_coop_xp(
    db: AsyncSession, task: ScnTaskInstance, *, final_xp: int, assignee: SysChild,
) -> tuple[dict, list]:
    """COOP XP 一次性结算(docs/13 定稿版 §6,DEV-40)。

    分母 = **最终交付的孩子参与者数**(裁决 Q4:家长 SUBMITTED 不入分母、
    未交付/退出的孩子不分)。XP 在聚合终结时(整单通过 / 部分通过判退收尾 /
    全员 DONE)一次算清——逐人 approve 时点无法预知最终分母,提前落账必错。
    """
    delivered = coop_service.delivered_children(task)
    xp_shares = coop_service.split_evenly(final_xp, len(delivered)) if delivered else []
    xp_results: list[dict] = []
    unlocked_privileges: list = []
    for i, p in enumerate(delivered):
        share = xp_shares[i]
        p_child = await db.get(SysChild, p.child_id)
        if p_child is None:
            continue
        info = xp_service.apply_xp_and_level(p_child, share)
        p.xp_awarded = share
        xp_results.append(info)
        unlocked = await privilege_service.unlock_for_user(db, p_child)
        unlocked_privileges.extend(unlocked)
    level_info = xp_results[0] if xp_results else xp_service.apply_xp_and_level(assignee, 0)
    return level_info, unlocked_privileges


async def _approve_coop_participant(
    db: AsyncSession, task: ScnTaskInstance, *, family_id: str, rating: int,
    comment: str | None, child_id: str | None, participant_id: str | None,
) -> tuple[ScnTaskInstance, SysChild, dict]:
    """逐人确认(docs/13 定稿版 §3.1):带 child_id / participant_id 的 approve。

    入口状态 = IN_PROGRESS 或 PENDING_REVIEW,守卫 = 该参与者 SUBMITTED。
    押金即时结算(退份额);XP 不在此结算,延后到聚合终结一次算清(§6)。
    全员 DONE → 实例聚合 COMPLETED 并执行 XP 结算。
    """
    if task.status not in (TaskStatus.IN_PROGRESS, TaskStatus.PENDING_REVIEW):
        raise ConflictError(f"当前状态 {_enum_value(task.status)},无法逐人确认")
    participant = coop_service.find_participant(
        task, child_id=child_id, participant_id=participant_id,
    )
    if participant is None or participant.confirmed_at is None:
        raise NotFoundError("该任务没有此参与者")
    status = coop_service.participant_status_of(participant)
    if status == TaskParticipantStatus.DONE:
        raise ConflictError("该参与者已确认过")
    if status != TaskParticipantStatus.SUBMITTED:
        raise ConflictError("该参与者尚未提交,无法逐人确认")

    participant.participant_status = TaskParticipantStatus.DONE.value
    refunded_now = 0
    if participant.child_id:
        p_child = await db.get(SysChild, participant.child_id)
        if p_child is not None and participant.deposit_share > 0:
            p_child.time_coin_balance += participant.deposit_share
            await coin_service.record_transaction(
                db,
                child=p_child,
                type=CoinTransactionType.TASK_REFUND,
                amount=participant.deposit_share,
                task_instance_id=task.id,
                note="协作任务逐人确认退还押金份额",
            )
            refunded_now = participant.deposit_share
    task.rating = rating
    task.review_comment = comment

    assignee = await _ensure_child(db, family_id=family_id, child_id=task.assignee_child_id)
    settle_info: dict = {
        "participant": {
            "child_id": participant.child_id,
            "role": _enum_value(participant.role),
            "participant_status": TaskParticipantStatus.DONE.value,
            "deposit_refunded": refunded_now,
        },
    }

    if all(
        coop_service.participant_status_of(p) == TaskParticipantStatus.DONE
        for p in task.participants
    ):
        # 聚合终结:全员 DONE → COMPLETED,XP 按最终交付孩子数一次结算(docs/13 §6)
        final_xp = _coop_final_xp(task, rating=rating)
        task.status = TaskStatus.COMPLETED
        task.xp_awarded = final_xp
        task.completed_at = utcnow()
        # coin_delta = 实例生命周期累计实退(逐人确认步已退的份额已在先前累加)
        task.coin_delta = (task.coin_delta or 0) + sum(
            p.deposit_share for p in coop_service.wallet_participants(task)
        )
        level_info, unlocked_privileges = await _settle_coop_xp(
            db, task, final_xp=final_xp, assignee=assignee,
        )
        await chain_service.spawn_next_chain_step(db, task)
        await db.commit()
        await db.refresh(task)
        await db.refresh(assignee)
        settle_info.update({
            "aggregated": True,
            "xp_awarded": final_xp,
            "deposit_refunded": task.coin_delta,
            "unlocked_privilege_count": len(unlocked_privileges),
            **level_info,
        })
    else:
        # coin_delta = 实例生命周期累计实退(逐人步累加,聚合终结步继续累加)
        task.coin_delta = (task.coin_delta or 0) + refunded_now
        await db.commit()
        await db.refresh(task)
        await db.refresh(assignee)
        settle_info.update({"aggregated": False, "xp_awarded": 0, "deposit_refunded": refunded_now})
    return task, assignee, settle_info


def _coop_final_xp(task: ScnTaskInstance, *, rating: int) -> int:
    """聚合终结时的最终 XP(参数与整单审批同一套:难度/时间窗/链末加成)。"""
    template = task.template
    required_start_time = template.required_start_time if template else None
    is_challenge = bool(template and template.type == TaskType.CHALLENGE)
    difficulty = template.difficulty if template is not None else None
    return xp_service.calculate_xp(
        task.xp_reward,
        rating=rating,
        difficulty=difficulty,
        started_at=task.started_at,
        submitted_at=task.submitted_at,
        required_start_time=required_start_time,
        is_challenge=is_challenge,
        chain_index=task.chain_index,
        chain_total=task.chain_total,
    )


async def _approve_coop_partial_settle(
    db: AsyncSession, task: ScnTaskInstance, *, rating: int, comment: str | None,
) -> tuple[ScnTaskInstance, SysChild, dict]:
    """部分通过判退收尾(docs/13 定稿版 §3.1 / §5 裁决 Q1)。

    入口 = IN_PROGRESS + 存在至少一名 SUBMITTED;显式 settle_partial=True 才进本路径
    (漏传标志的整单 approve 在 IN_PROGRESS 下 409,判退真金白银打折退款必须显式确认)。
    - SUBMITTED:押金退份额、子状态 → DONE;
    - JOINED:视为 QUIT,押金按放弃阶梯打折退,**不递增当日放弃计数**(裁决 Q1);
    - XP 按最终交付孩子数一次结算(裁决 Q4),实例终结 COMPLETED。
    """
    if task.status != TaskStatus.IN_PROGRESS:
        raise ConflictError(
            f"部分通过判退仅限 IN_PROGRESS(当前 {_enum_value(task.status)};"
            "全员已交请直接整单审批)"
        )
    if not coop_service.delivered_participants(task):
        raise ValidationError("没有已提交的参与者,无可部分通过;未开始请走放弃任务")

    # family 归属已由 approve_task 入口校验(task.family_id == family_id),
    # 这里按任务上的 family_id 取主接取人
    assignee = (
        await _ensure_child(db, family_id=task.family_id, child_id=task.assignee_child_id)
        if task.assignee_child_id else None
    )
    if assignee is None:
        raise ValidationError("任务没有接取人")

    judged: list[ScnTaskParticipant] = []
    total_refund = 0
    for p in task.participants:
        status = coop_service.participant_status_of(p)
        if status == TaskParticipantStatus.SUBMITTED:
            p.participant_status = TaskParticipantStatus.DONE.value
            if p.child_id and p.deposit_share > 0:
                p_child = await db.get(SysChild, p.child_id)
                if p_child is not None:
                    p_child.time_coin_balance += p.deposit_share
                    await coin_service.record_transaction(
                        db,
                        child=p_child,
                        type=CoinTransactionType.TASK_REFUND,
                        amount=p.deposit_share,
                        task_instance_id=task.id,
                        note="协作任务部分通过,退还押金份额",
                    )
                    total_refund += p.deposit_share
        elif status == TaskParticipantStatus.JOINED:
            # 部分通过判退:按放弃阶梯打折退,但不递增当日放弃计数
            # (判退是家长收尾动作,不是孩子的主动放弃,一次行为不双重惩罚)
            p.participant_status = TaskParticipantStatus.QUIT.value
            if p.child_id and p.deposit_share > 0:
                p_child = await db.get(SysChild, p.child_id)
                if p_child is not None:
                    refund = coin_service.calculate_refund(
                        p.deposit_share, p_child.daily_abandon_count
                    )
                    if refund >= p.deposit_share:
                        note = "[部分通过判退] 押金份额已全额退还"
                    else:
                        percent = int(refund * 100 / p.deposit_share)
                        note = (
                            f"[部分通过判退] 当日已放弃 {p_child.daily_abandon_count} 次,"
                            f"按 {percent}% 退还"
                        )
                    p_child.time_coin_balance += refund
                    await coin_service.record_transaction(
                        db,
                        child=p_child,
                        type=CoinTransactionType.TASK_REFUND,
                        amount=refund,
                        task_instance_id=task.id,
                        note=note,
                    )
                    total_refund += refund
                    penalty = p.deposit_share - refund
                    if penalty > 0:
                        await coin_service.record_transaction(
                            db,
                            child=p_child,
                            type=CoinTransactionType.ABANDON_PENALTY,
                            amount=-penalty,
                            task_instance_id=task.id,
                            note="[部分通过判退] 未交付押金扣罚",
                        )
                    judged.append(p)
        # DONE:逐人确认时已结算,不动(防双退)

    final_xp = _coop_final_xp(task, rating=rating)
    task.status = TaskStatus.COMPLETED
    task.rating = rating
    task.review_comment = comment
    task.xp_awarded = final_xp
    task.completed_at = utcnow()
    # coin_delta = 实例生命周期累计实退(判退步实退 + 先前逐人步已退累加)
    task.coin_delta = (task.coin_delta or 0) + total_refund
    level_info, unlocked_privileges = await _settle_coop_xp(
        db, task, final_xp=final_xp, assignee=assignee,
    )
    await chain_service.spawn_next_chain_step(db, task)

    # 通知被判退者,内容带退款解释(实现期补充要求:孩子要能看懂"为什么退少了")
    _notify_coop_participants(
        db, task,
        type_=NotificationType.COOP_PARTIAL_SETTLED,
        recipient_participants=judged,
        title="协作任务已部分通过结算",
        body=(
            f"任务「{task.title}」家长已按已交付部分结算。"
            "你未交付本人份额,押金按当日放弃规则退还,详见时间币流水。"
        ),
        payload={"task_instance_id": task.id, "outcome": "PARTIAL_SETTLED"},
    )

    await db.commit()
    await db.refresh(task)
    await db.refresh(assignee)
    return task, assignee, {
        "aggregated": True,
        "partial_settled": True,
        "xp_awarded": final_xp,
        "deposit_refunded": total_refund,
        "judged_quit": [
            {"child_id": p.child_id, "deposit_share": p.deposit_share} for p in judged
        ],
        "unlocked_privilege_count": len(unlocked_privileges),
        **level_info,
    }


async def approve_task(
    db: AsyncSession, *, task_id: str, family_id: str, rating: int, comment: str | None = None,
    child_id: str | None = None, participant_id: str | None = None,
    settle_partial: bool = False,
) -> tuple[ScnTaskInstance, SysChild, dict]:
    """父母审核(docs/13 定稿版 §3.1/§4,DEV-40):

    - 带 `child_id`(或家长参与者的 `participant_id`)→ 逐人确认;
    - `settle_partial=True` → 部分通过判退收尾(仅 IN_PROGRESS);
    - 都不带 → 整单通过(仅 PENDING_REVIEW,现行为;单人任务唯一路径)。
    行锁(get_task_for_update)保证与 COOP join / 并发双审批互斥。
    """
    task = await get_task_for_update(db, task_id)
    if task.family_id != family_id:
        raise PermissionDeniedError("只能审核自己家庭的任务")
    coop = coop_service.is_coop(task)

    if child_id is not None or participant_id is not None:
        if not coop:
            raise ValidationError("单人任务不支持逐人确认")
        return await _approve_coop_participant(
            db, task, family_id=family_id, rating=rating, comment=comment,
            child_id=child_id, participant_id=participant_id,
        )
    if settle_partial:
        if not coop:
            raise ValidationError("单人任务不支持部分通过判退")
        return await _approve_coop_partial_settle(db, task, rating=rating, comment=comment)
    if coop and task.status == TaskStatus.IN_PROGRESS:
        # IN_PROGRESS 下尚有未交者:整单 approve 会把未交付者静默判退,
        # 必须显式 settle_partial 确认(docs/13 §3.1)
        raise ConflictError(
            "仍有参与者未提交;如需按已交付部分收尾,请显式传入 settle_partial=true"
        )
    if task.status != TaskStatus.PENDING_REVIEW:
        raise ConflictError(f"当前状态 {_enum_value(task.status)},无法审核")
    if not task.assignee_child_id:
        raise ValidationError("任务没有接取人")

    assignee = await _ensure_child(db, family_id=family_id, child_id=task.assignee_child_id)
    final_xp = _coop_final_xp(task, rating=rating)
    task.status = TaskStatus.COMPLETED
    task.rating = rating
    task.review_comment = comment
    task.xp_awarded = final_xp
    task.completed_at = utcnow()

    unlocked_privileges: list = []
    if coop:
        # 整单通过:结算所有未确认的 SUBMITTED 参与者(逐人确认过的 DONE 不重复退);
        # PENDING_REVIEW 下无 JOINED(进该状态要求全员已交)
        total_refund = 0
        for p in task.participants:
            if coop_service.participant_status_of(p) != TaskParticipantStatus.SUBMITTED:
                continue
            p.participant_status = TaskParticipantStatus.DONE.value
            if p.child_id and p.deposit_share > 0:
                p_child = await db.get(SysChild, p.child_id)
                if p_child is not None:
                    p_child.time_coin_balance += p.deposit_share
                    await coin_service.record_transaction(
                        db,
                        child=p_child,
                        type=CoinTransactionType.TASK_REFUND,
                        amount=p.deposit_share,
                        task_instance_id=task.id,
                        note="协作任务完成退还押金份额",
                    )
                    total_refund += p.deposit_share
        # XP 按最终交付孩子数一次结算(裁决 Q4,行为修改:原为全部已确认孩子均摊)
        level_info, unlocked_privileges = await _settle_coop_xp(
            db, task, final_xp=final_xp, assignee=assignee,
        )
        # coin_delta = 实例生命周期累计实退(本步实退 + 先前逐人步已退累加)
        task.coin_delta = (task.coin_delta or 0) + total_refund
        settle_info = {
            "participants": [
                {
                    "child_id": p.child_id,
                    "role": p.role.value if hasattr(p.role, "value") else str(p.role),
                    "participant_status": p.participant_status,
                    "deposit_refunded": p.deposit_share
                    if coop_service.participant_status_of(p) == TaskParticipantStatus.DONE
                    and p.child_id
                    else 0,
                    "xp_awarded": p.xp_awarded,
                }
                for p in task.participants
            ],
        }
    else:
        level_info = xp_service.apply_xp_and_level(assignee, final_xp)
        unlocked_privileges = await privilege_service.unlock_for_user(db, assignee)

        deposit = _deposit_of(task)
        assignee.time_coin_balance += deposit
        await coin_service.record_transaction(
            db,
            child=assignee,
            type=CoinTransactionType.TASK_REFUND,
            amount=deposit,
            task_instance_id=task.id,
            note="任务完成退还押金",
        )
        task.coin_delta = deposit
        settle_info = {}

    # CHAIN:第 N 步 COMPLETED -> 生成第 N+1 步。
    # 唯一接线点在 chain_service.spawn_next_chain_step(DEV-35 合入后只改那一处)。
    await chain_service.spawn_next_chain_step(db, task)

    await db.commit()
    await db.refresh(task)
    await db.refresh(assignee)
    return task, assignee, {
        "xp_awarded": final_xp,
        "deposit_refunded": task.coin_delta,
        "unlocked_privilege_count": len(unlocked_privileges),
        **level_info,
        **settle_info,
    }


async def reject_task(
    db: AsyncSession, *, task_id: str, family_id: str, comment: str | None = None,
) -> ScnTaskInstance:
    """父母审核驳回:状态切回 IN_PROGRESS,不动押金,孩子可修改后重新提交。

    COOP(docs/13 定稿版 §3.1):未结算的 SUBMITTED 参与者回 JOINED、可重新提交;
    已落 proof 行保留(审计链),重新提交追加新行,审核以最新一轮为准;
    已 DONE 的参与者不受影响(逐人确认即时结算后不回滚)。
    行锁与并发 approve/reject 互斥(与整单审批同一把实例行锁)。
    """
    task = await get_task_for_update(db, task_id)
    if task.family_id != family_id:
        raise PermissionDeniedError("只能审核自己家庭的任务")
    if task.status != TaskStatus.PENDING_REVIEW:
        raise ConflictError(f"当前状态 {_enum_value(task.status)},无法驳回")

    task.status = TaskStatus.IN_PROGRESS
    task.review_comment = comment
    task.submitted_at = None

    if coop_service.is_coop(task):
        for p in task.participants:
            if coop_service.participant_status_of(p) == TaskParticipantStatus.SUBMITTED:
                p.participant_status = TaskParticipantStatus.JOINED.value

    now = utcnow()
    if task.expire_at is not None and task.expire_at <= now:
        task.expire_at = now + REJECT_RESUBMIT_GRACE

    await db.commit()
    await db.refresh(task)
    return task


async def leave_task(
    db: AsyncSession, *, task_id: str, user: SysAccount,
) -> ScnTaskInstance:
    """参与者退出协作任务(docs/13 定稿版 §4/§5,DEV-40)。

    - 仅 COOP、仅 IN_PROGRESS;主接取人(OWNER)不走本接口,用整体 abandon;
    - 押金按该参与者当日放弃次数打折退(`calculate_refund`),**递增**其当日
      放弃计数(主动放弃行为,与部分通过判退的"不递增"相对,docs/13 §5);
    - 子状态 → QUIT,参与者行保留作审计;已落 proof 保留;
    - 实例与其余参与者不动,其余参与者仍可继续交卷/被逐人确认。
    """
    task = await get_task_for_update(db, task_id)
    if task.family_id != user.family_id:
        raise PermissionDeniedError("只能操作自己家庭的任务")
    if not coop_service.is_coop(task):
        raise ValidationError("只有协作任务支持参与者退出")
    if task.status != TaskStatus.IN_PROGRESS:
        raise ConflictError(f"当前状态 {_enum_value(task.status)},无法退出")
    participant = coop_service.find_participant(task, account_id=user.id)
    if participant is None or participant.confirmed_at is None:
        raise PermissionDeniedError("你不是该协作任务的参与者")
    if participant.role == TaskParticipantRole.OWNER:
        raise ConflictError("主接取人请使用放弃任务(整体退出)")
    status = coop_service.participant_status_of(participant)
    if status in (TaskParticipantStatus.DONE, TaskParticipantStatus.QUIT):
        raise ConflictError("你已确认完成或已退出,无需重复操作")

    if participant.child_id and participant.deposit_share > 0:
        child = await db.get(SysChild, participant.child_id)
        if child is not None:
            refund = coin_service.calculate_refund(
                participant.deposit_share, child.daily_abandon_count
            )
            if refund >= participant.deposit_share:
                note = "[放弃] 退出协作任务,押金份额已全额退还"
            else:
                percent = int(refund * 100 / participant.deposit_share)
                note = (
                    f"[放弃] 退出协作任务,当日已放弃 {child.daily_abandon_count} 次,"
                    f"按 {percent}% 退还"
                )
            child.time_coin_balance += refund
            await coin_service.record_transaction(
                db,
                child=child,
                type=CoinTransactionType.TASK_REFUND,
                amount=refund,
                task_instance_id=task.id,
                note=note,
            )
            penalty = participant.deposit_share - refund
            if penalty > 0:
                await coin_service.record_transaction(
                    db,
                    child=child,
                    type=CoinTransactionType.ABANDON_PENALTY,
                    amount=-penalty,
                    task_instance_id=task.id,
                    note="[放弃] 退出协作任务惩罚",
                )
            child.daily_abandon_count += 1  # 主动放弃行为:递增计数(docs/13 §5)

    participant.participant_status = TaskParticipantStatus.QUIT.value
    await db.commit()
    await db.refresh(task)
    return task


async def abandon_task(
    db: AsyncSession, *, task_id: str, user: SysAccount,
) -> tuple[ScnTaskInstance, SysChild, int]:
    """孩子放弃:按规则退款(连续 3 次后 60% 退款)。行锁与 COOP join 互斥。"""
    child = await _account_child(db, user)
    task = await get_task_for_update(db, task_id)
    if task.family_id != user.family_id:
        raise PermissionDeniedError("只能操作自己家庭的任务")
    if task.assignee_child_id != child.id:
        raise PermissionDeniedError("你不是该任务的接取人")
    if task.status != TaskStatus.IN_PROGRESS:
        raise ConflictError(f"当前状态 {_enum_value(task.status)},无法放弃")

    if coop_service.is_coop(task):
        # COOP 放弃:发起放弃的主接取人按连续放弃规则打折退款并计数;
        # 其他参与者未发起放弃,全额退还份额,不计入其惩罚。
        # 参与者行随放弃清除,任务回 AVAILABLE 后可重新接取/加入;
        # 参与者"各自交付"的中间态结算见 docs/13 定稿版(逐人 approve / leave,
        # DEV-40 已实现)——整体 abandon 保留给主接取人收尾整单。
        total_refund = 0
        for p in coop_service.wallet_participants(task):
            # 已逐人确认(DONE)的参与者结算已发生,跳过防双退
            # (DEV-40 审查 🔴:B 被逐人 approve 后 OWNER abandon,不查子状态会再退一次)
            if coop_service.participant_status_of(p) == TaskParticipantStatus.DONE:
                continue
            p_child = await db.get(SysChild, p.child_id)
            if p_child is None:
                continue
            if p.child_id == child.id:
                refund = coin_service.calculate_refund(p.deposit_share, child.daily_abandon_count)
            else:
                refund = p.deposit_share
            p_child.time_coin_balance += refund
            await coin_service.record_transaction(
                db,
                child=p_child,
                type=CoinTransactionType.TASK_REFUND,
                amount=refund,
                task_instance_id=task.id,
                note="放弃协作任务退还押金份额",
            )
            total_refund += refund
            penalty = p.deposit_share - refund
            if penalty > 0:
                await coin_service.record_transaction(
                    db,
                    child=p_child,
                    type=CoinTransactionType.ABANDON_PENALTY,
                    amount=-penalty,
                    task_instance_id=task.id,
                    note="连续放弃任务惩罚",
                )
        child.daily_abandon_count += 1
        task.participants.clear()
        task.coin_delta = total_refund - _deposit_of(task)
    else:
        deposit = _deposit_of(task)
        refund = coin_service.calculate_refund(deposit, child.daily_abandon_count)
        child.time_coin_balance += refund
        await coin_service.record_transaction(
            db,
            child=child,
            type=CoinTransactionType.TASK_REFUND,
            amount=refund,
            task_instance_id=task.id,
            note="放弃任务退还押金",
        )
        penalty = deposit - refund
        if penalty > 0:
            await coin_service.record_transaction(
                db,
                child=child,
                type=CoinTransactionType.ABANDON_PENALTY,
                amount=-penalty,
                task_instance_id=task.id,
                note="连续放弃任务惩罚",
            )
        child.daily_abandon_count += 1
        task.coin_delta = refund - deposit

    task.status = TaskStatus.AVAILABLE
    task.assignee_child_id = None
    task.started_at = None

    await db.commit()
    await db.refresh(task)
    await db.refresh(child)
    return task, child, task.coin_delta


async def delete_task(db: AsyncSession, *, task_id: str, family_id: str | None = None) -> None:
    t = await get_task(db, task_id)
    if family_id is not None and t.family_id != family_id:
        raise PermissionDeniedError("只能删除自己家庭的任务")
    await db.delete(t)
    await db.commit()


async def _notify_task_expired(db: AsyncSession, *, task: ScnTaskInstance, child: SysChild | None) -> None:
    """任务过期站内通知(INAPP 直写即达,记 SENT;无独立投递器,微信通道暂不涉及)。"""
    recipient_account_id = child.account_id if child is not None else task.creator_account_id
    if recipient_account_id is None:
        return
    db.add(ScnNotification(
        family_id=task.family_id,
        recipient_account_id=recipient_account_id,
        channel=NotificationChannel.INAPP,
        type=NotificationType.TASK_EXPIRED,
        title="任务已过期",
        body=f"任务「{task.title}」已超过截止时间,系统已将其标记为过期。",
        payload={"task_instance_id": task.id, "status": TaskStatus.EXPIRED.value},
        status=NotificationStatus.SENT,
        sent_at=utcnow(),
    ))


async def expire_overdue_tasks(db: AsyncSession, *, now: datetime | None = None) -> int:
    """过期任务处理:AVAILABLE/IN_PROGRESS 且 expire_at 已过的任务统一切 EXPIRED。

    - AVAILABLE(未接取):直接过期,不涉及押金(未扣押金,无退还/扣罚)。
    - IN_PROGRESS(已接取未提交):退押金 `timeout_refund_ratio`(默认 50%),
      其余作为 `TIMEOUT_PENALTY` 扣罚;不计入连续放弃惩罚
      (`daily_abandon_count` 不变),避免"截止时间到了"和"孩子自己放弃"
      共用同一条惩罚路径;并发 `TASK_EXPIRED` 通知。
    - PENDING_REVIEW/COMPLETED/EXPIRED 不受影响:已提交等待审核的任务由家长
      决定审核或驳回,不应被系统静默判过期。
    - 非限时任务(`expire_at IS NULL`)不参与过期(走顺延逻辑)。

    供定时任务(`app.workers.scheduler`)调用,亦可在测试/运维中手动触发。
    返回本次处理的任务数量。
    """
    now = now or utcnow()
    stmt = (
        select(ScnTaskInstance)
        .where(
            ScnTaskInstance.expire_at.is_not(None),
            ScnTaskInstance.expire_at < now,
            ScnTaskInstance.status.in_([TaskStatus.AVAILABLE, TaskStatus.IN_PROGRESS]),
        )
        # 行锁:COOP 过期结算(按参与者份额退款)与 join 的重摊互斥(MR #10 审查 🔴)
        .with_for_update(skip_locked=True)
        .options(selectinload(ScnTaskInstance.template))
    )
    tasks = list((await db.execute(stmt)).scalars().all())

    processed = 0
    for task in tasks:
        child: SysChild | None = None
        if task.status == TaskStatus.IN_PROGRESS and task.assignee_child_id:
            if coop_service.is_coop(task):
                # COOP 过期:已确认的钱包参与者各自全额退还份额,不计放弃惩罚。
                # 注意:与 abandon 不同,这里**不清** participant 行——EXPIRED 目前是
                # 终态,行保留作审计;若 DEV-35 池将来复用过期实例,必须在复活时
                # 清行/重置份额,否则按行结算会双退(MR #10 审查备注)。
                # (DEV-41 集成注:单人路径按 DEV-34 块 C+D 语义退 50%/扣罚 50%;
                # COOP 全额退还是块 F 已过审口径,两口径并存,后续统一待议。)
                refunded = 0
                for p in coop_service.wallet_participants(task):
                    # 已逐人确认(DONE)的参与者结算已发生,跳过防双退(DEV-40 审查 🔴)
                    if coop_service.participant_status_of(p) == TaskParticipantStatus.DONE:
                        continue
                    p_child = await db.get(SysChild, p.child_id)
                    if p_child is None:
                        continue
                    p_child.time_coin_balance += p.deposit_share
                    await coin_service.record_transaction(
                        db,
                        child=p_child,
                        type=CoinTransactionType.TASK_REFUND,
                        amount=p.deposit_share,
                        task_instance_id=task.id,
                        note="协作任务过期退还押金份额",
                    )
                    refunded += p.deposit_share
                # 本次实退累计(不含逐人步已退的 DONE 份额)
                task.coin_delta = refunded
            else:
                child = await db.get(SysChild, task.assignee_child_id)
                if child is not None:
                    # 单人超时(DEV-34 块 C+D):退 timeout_refund_ratio(默认 50%),
                    # 其余 TIMEOUT_PENALTY 扣罚——不得回退为全额退还。
                    deposit = task.time_deposit
                    refund = coin_service.calculate_timeout_refund(deposit)
                    child.time_coin_balance += refund
                    await coin_service.record_transaction(
                        db,
                        child=child,
                        type=CoinTransactionType.TASK_REFUND,
                        amount=refund,
                        task_instance_id=task.id,
                        note="任务超时退还部分押金",
                    )
                    penalty = deposit - refund
                    if penalty > 0:
                        await coin_service.record_transaction(
                            db,
                            child=child,
                            type=CoinTransactionType.TIMEOUT_PENALTY,
                            amount=-penalty,
                            task_instance_id=task.id,
                            note="任务超时未提交扣罚",
                        )
                    task.coin_delta = refund - deposit
        task.status = TaskStatus.EXPIRED
        await _notify_task_expired(db, task=task, child=child)
        processed += 1

    if processed:
        await db.commit()
    return processed
