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
from app.models.enums import (
    CoinTransactionType,
    NotificationChannel,
    NotificationStatus,
    NotificationType,
    TaskParticipantRole,
    TaskStatus,
    TaskType,
    UploadPurpose,
    UserRole,
)
from app.models.scn_notification import ScnNotification
from app.models.scn_season import ScnSeason
from app.models.scn_task_instance import ScnTaskInstance
from app.models.scn_task_participant import ScnTaskParticipant
from app.models.scn_task_template import ScnTaskTemplate
from app.models.scn_task_template_library import ScnTaskTemplateLibrary
from app.models.sys_account import SysAccount
from app.models.sys_child import SysChild
from app.models.sys_upload import SysUpload
from app.services import chain_service, coin_service, coop_service, privilege_service, xp_service

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
    db: AsyncSession, *, task_id: str, user: SysAccount, proof_object_key: str,
) -> ScnTaskInstance:
    """孩子提交:状态切 PENDING_REVIEW。"""
    child = await _account_child(db, user)
    task = await get_task(db, task_id)
    if task.family_id != user.family_id:
        raise PermissionDeniedError("只能操作自己家庭的任务")
    if task.assignee_child_id != child.id:
        raise PermissionDeniedError("你不是该任务的接取人")
    if task.status != TaskStatus.IN_PROGRESS:
        raise ConflictError(f"当前状态 {_enum_value(task.status)},无法提交")
    # 归属校验(Mars 审查 🟡):证明 key 必须是当前用户本人上传的 task_proof 凭证。
    # 不校验时,local 模式下 key 直接映射静态文件路径,提交任意字符串即可引用/探测他人对象。
    upload = (
        await db.execute(
            select(SysUpload).where(
                SysUpload.object_key == proof_object_key,
                SysUpload.uploader_account_id == user.id,
                SysUpload.purpose == UploadPurpose.TASK_PROOF,
            )
        )
    ).scalar_one_or_none()
    if upload is None:
        raise ValidationError("证明文件不存在、不是任务凭证或不属于当前用户")
    # 任务关联(DEV-30):上传时未带 task_id 的凭证在提交时回填绑定,
    # 保证 sys_upload 数据库层始终可按任务检索;已绑定其他任务的凭证拒绝复用。
    if upload.task_instance_id is None:
        upload.task_instance_id = task.id
    elif upload.task_instance_id != task.id:
        raise ValidationError("该证明文件已关联其他任务,请重新上传")
    task.status = TaskStatus.PENDING_REVIEW
    task.proof_object_key = proof_object_key
    task.submitted_at = utcnow()
    task.abandon_count_at_submit = child.daily_abandon_count
    await db.commit()
    await db.refresh(task)
    return task


async def approve_task(
    db: AsyncSession, *, task_id: str, family_id: str, rating: int, comment: str | None = None,
) -> tuple[ScnTaskInstance, SysChild, dict]:
    """父母审核:状态切 COMPLETED,发 XP + 退押金。行锁(get_task_for_update)
    保证与 COOP join / 并发双审批互斥。"""
    task = await get_task_for_update(db, task_id)
    if task.family_id != family_id:
        raise PermissionDeniedError("只能审核自己家庭的任务")
    if task.status != TaskStatus.PENDING_REVIEW:
        raise ConflictError(f"当前状态 {_enum_value(task.status)},无法审核")
    if not task.assignee_child_id:
        raise ValidationError("任务没有接取人")

    assignee = await _ensure_child(db, family_id=family_id, child_id=task.assignee_child_id)
    template = task.template
    required_start_time = template.required_start_time if template else None
    is_challenge = bool(template and template.type == TaskType.CHALLENGE)
    difficulty = template.difficulty if template is not None else None
    final_xp = xp_service.calculate_xp(
        task.xp_reward,
        rating=rating,
        difficulty=difficulty,
        started_at=task.started_at,
        submitted_at=task.submitted_at,
        required_start_time=required_start_time,
        is_challenge=is_challenge,
        # CHAIN 链末步骤(chain_index == chain_total)享受链末加成(docs/04 §2.3)
        chain_index=task.chain_index,
        chain_total=task.chain_total,
    )
    task.status = TaskStatus.COMPLETED
    task.rating = rating
    task.review_comment = comment
    task.xp_awarded = final_xp
    task.completed_at = utcnow()

    settle_info: dict = {}
    unlocked_privileges: list = []
    if coop_service.is_coop(task):
        wallets = coop_service.wallet_participants(task)
        # XP 在孩子参与者间均摊(家长参与者不获得 XP,也不占份额)
        xp_shares = coop_service.split_evenly(final_xp, len(wallets)) if wallets else []
        xp_results = []
        for i, p in enumerate(wallets):
            share = xp_shares[i]
            p_child = await db.get(SysChild, p.child_id)
            if p_child is None:
                continue
            info = xp_service.apply_xp_and_level(p_child, share)
            p.xp_awarded = share
            xp_results.append(info)
            # 押金按各自份额退还
            p_child.time_coin_balance += p.deposit_share
            await coin_service.record_transaction(
                db,
                child=p_child,
                type=CoinTransactionType.TASK_REFUND,
                amount=p.deposit_share,
                task_instance_id=task.id,
                note="协作任务完成退还押金份额",
            )
            unlocked = await privilege_service.unlock_for_user(db, p_child)
            unlocked_privileges.extend(unlocked)
        level_info = xp_results[0] if xp_results else xp_service.apply_xp_and_level(assignee, 0)
        total_refund = sum(p.deposit_share for p in wallets)
        task.coin_delta = total_refund
        settle_info = {
            "participants": [
                {
                    "child_id": p.child_id,
                    "role": p.role.value if hasattr(p.role, "value") else str(p.role),
                    "deposit_refunded": p.deposit_share,
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
    """父母审核驳回:状态切回 IN_PROGRESS,不动押金,孩子可修改后重新提交。"""
    task = await get_task(db, task_id)
    if task.family_id != family_id:
        raise PermissionDeniedError("只能审核自己家庭的任务")
    if task.status != TaskStatus.PENDING_REVIEW:
        raise ConflictError(f"当前状态 {_enum_value(task.status)},无法驳回")

    task.status = TaskStatus.IN_PROGRESS
    task.review_comment = comment
    task.submitted_at = None

    now = utcnow()
    if task.expire_at is not None and task.expire_at <= now:
        task.expire_at = now + REJECT_RESUBMIT_GRACE

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
        # 更细的"部分完成"结算见 docs/13 设计草案(待独立立项实现)。
        total_refund = 0
        for p in coop_service.wallet_participants(task):
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
                task.coin_delta = 0
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
