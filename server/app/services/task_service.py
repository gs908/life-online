"""任务服务:模板/实例 + 状态机 + 押金/退款 + 审批。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.common.exceptions import ConflictError, NotFoundError, PermissionDeniedError, ValidationError
from app.models.enums import CoinTransactionType, TaskStatus, TaskType, UserRole
from app.models.scn_season import ScnSeason
from app.models.scn_task_instance import ScnTaskInstance
from app.models.scn_task_template import ScnTaskTemplate
from app.models.sys_account import SysAccount
from app.models.sys_child import SysChild
from app.services import coin_service, privilege_service, xp_service


def _enum_value(value) -> str:
    return value.value if hasattr(value, "value") else str(value)


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


async def create_task(db: AsyncSession, *, family_id: str, creator_id: str, **kwargs) -> ScnTaskInstance:
    """兼容旧 create_task API:同时创建模板与一条初始实例。"""
    target_child_id = kwargs.pop("target_child_id", None) or kwargs.pop("target_user_id", None)
    season_id = kwargs["season_id"]
    await _ensure_task_refs(
        db,
        family_id=family_id,
        season_id=season_id,
        target_child_id=target_child_id,
    )

    template = ScnTaskTemplate(
        family_id=family_id,
        season_id=season_id,
        creator_account_id=creator_id,
        target_child_id=target_child_id,
        title=kwargs["title"],
        description=kwargs.get("description", ""),
        lore_snippet=kwargs.get("lore_snippet"),
        xp_reward=kwargs.get("xp_reward", 50),
        type=kwargs.get("type"),
        required_start_time=kwargs.get("required_start_time"),
        reminder_message=kwargs.get("reminder_message"),
        reminder_minutes_before=kwargs.get("reminder_minutes_before", 15),
        time_deposit=kwargs.get("time_deposit", 10),
        is_active=True,
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
        time_deposit=template.time_deposit,
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
    offset: int = 0, limit: int | None = None,
) -> tuple[list[ScnTaskInstance], int]:
    stmt = select(ScnTaskInstance).where(ScnTaskInstance.family_id == family_id)
    if season_id is not None:
        stmt = stmt.where(ScnTaskInstance.season_id == season_id)
    if status is not None:
        stmt = stmt.where(ScnTaskInstance.status == status)
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

    deposit = coin_service.calculate_deposit_fee(task.time_deposit or 10)
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
    task.started_at = datetime.utcnow()
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
    task.status = TaskStatus.PENDING_REVIEW
    task.proof_object_key = proof_object_key
    task.submitted_at = datetime.utcnow()
    await db.commit()
    await db.refresh(task)
    return task


async def approve_task(
    db: AsyncSession, *, task_id: str, family_id: str, rating: int, comment: str | None = None,
) -> tuple[ScnTaskInstance, SysChild, dict]:
    """父母审核:状态切 COMPLETED,发 XP + 退押金。"""
    task = await get_task(db, task_id)
    if task.family_id != family_id:
        raise PermissionDeniedError("只能审核自己家庭的任务")
    if task.status != TaskStatus.PENDING_REVIEW:
        raise ConflictError(f"当前状态 {_enum_value(task.status)},无法审核")
    if not task.assignee_child_id:
        raise ValidationError("任务没有接取人")

    assignee = await _ensure_child(db, family_id=family_id, child_id=task.assignee_child_id)
    required_start_time = task.template.required_start_time if task.template else None
    is_challenge = bool(task.template and task.template.type == TaskType.CHALLENGE)
    final_xp = xp_service.calculate_xp(
        task.xp_reward,
        rating=rating,
        started_at=task.started_at,
        submitted_at=task.submitted_at,
        required_start_time=required_start_time,
        is_challenge=is_challenge,
    )
    level_info = xp_service.apply_xp_and_level(assignee, final_xp)
    unlocked_privileges = await privilege_service.unlock_for_user(db, assignee)

    deposit = task.time_deposit or 10
    assignee.time_coin_balance += deposit
    await coin_service.record_transaction(
        db,
        child=assignee,
        type=CoinTransactionType.TASK_REFUND,
        amount=deposit,
        task_instance_id=task.id,
        note="任务完成退还押金",
    )

    task.status = TaskStatus.COMPLETED
    task.rating = rating
    task.completed_at = datetime.utcnow()

    await db.commit()
    await db.refresh(task)
    await db.refresh(assignee)
    return task, assignee, {
        "xp_awarded": final_xp,
        "deposit_refunded": deposit,
        "unlocked_privilege_count": len(unlocked_privileges),
        **level_info,
    }


async def abandon_task(
    db: AsyncSession, *, task_id: str, user: SysAccount,
) -> tuple[ScnTaskInstance, SysChild, int]:
    """孩子放弃:按规则退款(连续 3 次后 60% 退款)。"""
    child = await _account_child(db, user)
    task = await get_task(db, task_id)
    if task.family_id != user.family_id:
        raise PermissionDeniedError("只能操作自己家庭的任务")
    if task.assignee_child_id != child.id:
        raise PermissionDeniedError("你不是该任务的接取人")
    if task.status != TaskStatus.IN_PROGRESS:
        raise ConflictError(f"当前状态 {_enum_value(task.status)},无法放弃")

    deposit = task.time_deposit or 10
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

    task.status = TaskStatus.AVAILABLE
    task.assignee_child_id = None
    task.started_at = None

    await db.commit()
    await db.refresh(task)
    await db.refresh(child)
    return task, child, refund


async def delete_task(db: AsyncSession, *, task_id: str, family_id: str | None = None) -> None:
    t = await get_task(db, task_id)
    if family_id is not None and t.family_id != family_id:
        raise PermissionDeniedError("只能删除自己家庭的任务")
    await db.delete(t)
    await db.commit()
