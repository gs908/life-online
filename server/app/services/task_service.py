"""任务服务:状态机 + 押金/退款 + 审批。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exceptions import ConflictError, NotFoundError, PermissionDeniedError, ValidationError
from app.models.enums import CoinTransactionType, TaskStatus, UserRole
from app.models.season import Season
from app.models.task import Task
from app.models.user import User
from app.services import coin_service, privilege_service, xp_service


async def _ensure_task_refs(db: AsyncSession, *, family_id: str, season_id: str, target_user_id: str | None) -> None:
    season = await db.get(Season, season_id)
    if not season:
        raise NotFoundError(f"赛季 {season_id} 不存在")
    if season.family_id != family_id:
        raise PermissionDeniedError("只能在自己家庭的赛季中创建任务")

    if target_user_id is None:
        return

    target = await db.get(User, target_user_id)
    if not target:
        raise NotFoundError(f"目标用户 {target_user_id} 不存在")
    if target.family_id != family_id:
        raise PermissionDeniedError("只能给自己家庭成员创建任务")
    if _enum_value(target.role) != UserRole.ADVENTURER.value:
        raise ValidationError("任务目标用户必须是 ADVENTURER")


async def create_task(db: AsyncSession, *, family_id: str, creator_id: str, **kwargs) -> Task:
    await _ensure_task_refs(
        db,
        family_id=family_id,
        season_id=kwargs["season_id"],
        target_user_id=kwargs.get("target_user_id"),
    )
    task = Task(
        family_id=family_id,
        creator_id=creator_id,
        status=TaskStatus.AVAILABLE,
        **kwargs,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


async def get_task(db: AsyncSession, task_id: str) -> Task:
    t = await db.get(Task, task_id)
    if not t:
        raise NotFoundError(f"任务 {task_id} 不存在")
    return t


async def list_tasks(
    db: AsyncSession, *, family_id: str, season_id: str | None = None,
    status: TaskStatus | None = None, assignee_id: str | None = None,
    offset: int = 0, limit: int | None = None,
) -> tuple[list[Task], int]:
    stmt = select(Task).where(Task.family_id == family_id)
    if season_id is not None:
        stmt = stmt.where(Task.season_id == season_id)
    if status is not None:
        stmt = stmt.where(Task.status == status)
    if assignee_id is not None:
        stmt = stmt.where(Task.assignee_id == assignee_id)

    total_stmt = select(func.count()).select_from(stmt.subquery())
    total = int((await db.execute(total_stmt)).scalar_one())

    stmt = stmt.order_by(Task.id.desc()).offset(offset)
    if limit is not None:
        stmt = stmt.limit(limit)
    items = list((await db.execute(stmt)).scalars().all())
    return items, total


def _enum_value(value) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _is_adventurer(user: User) -> bool:
    return _enum_value(user.role) == UserRole.ADVENTURER.value


async def start_task(
    db: AsyncSession, *, task_id: str, user: User,
) -> Task:
    """孩子接取任务:扣押金、状态切 IN_PROGRESS。"""
    task = await get_task(db, task_id)
    if task.family_id != user.family_id:
        raise PermissionDeniedError("只能操作自己家庭的任务")
    if not _is_adventurer(user):
        raise PermissionDeniedError("只有 ADVENTURER 可以接取任务")
    if task.status != TaskStatus.AVAILABLE:
        raise ConflictError(f"任务当前状态为 {_enum_value(task.status)},不可接取")
    if task.target_user_id and task.target_user_id != user.id:
        raise PermissionDeniedError("该任务指定了其他接取人")

    deposit = coin_service.calculate_deposit_fee(task.time_deposit or 10)
    if not coin_service.has_sufficient_coins(user, deposit):
        raise ValidationError(
            f"时间币不足,需要 {deposit},当前 {user.time_coins}"
        )

    user.time_coins -= deposit
    await coin_service.record_transaction(
        db,
        user=user,
        type=CoinTransactionType.TASK_DEPOSIT,
        amount=-deposit,
        task_id=task.id,
        note="接取任务扣除押金",
    )
    task.status = TaskStatus.IN_PROGRESS
    task.assignee_id = user.id
    task.started_at = datetime.utcnow()
    await db.commit()
    await db.refresh(task)
    return task


async def submit_task(
    db: AsyncSession, *, task_id: str, user: User, proof_object_key: str,
) -> Task:
    """孩子提交:状态切 PENDING_REVIEW。"""
    task = await get_task(db, task_id)
    if task.family_id != user.family_id:
        raise PermissionDeniedError("只能操作自己家庭的任务")
    if not _is_adventurer(user):
        raise PermissionDeniedError("只有 ADVENTURER 可以提交任务")
    if task.assignee_id != user.id:
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
) -> tuple[Task, User, dict]:
    """父母审核:状态切 COMPLETED,发 XP + 退押金。"""
    task = await get_task(db, task_id)
    if task.family_id != family_id:
        raise PermissionDeniedError("只能审核自己家庭的任务")
    if task.status != TaskStatus.PENDING_REVIEW:
        raise ConflictError(f"当前状态 {_enum_value(task.status)},无法审核")
    if not task.assignee_id:
        raise ValidationError("任务没有接取人")

    assignee = await db.get(User, task.assignee_id)
    if not assignee:
        raise NotFoundError(f"接取人 {task.assignee_id} 不存在")

    # 计算 XP
    final_xp = xp_service.calculate_xp(
        task.xp_reward,
        rating=rating,
        started_at=task.started_at,
        required_start_time=task.required_start_time,
    )
    level_info = xp_service.apply_xp_and_level(assignee, final_xp)
    unlocked_privileges = await privilege_service.unlock_for_user(db, assignee)

    # 退押金
    deposit = task.time_deposit or 10
    assignee.time_coins += deposit
    await coin_service.record_transaction(
        db,
        user=assignee,
        type=CoinTransactionType.TASK_REFUND,
        amount=deposit,
        task_id=task.id,
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
    db: AsyncSession, *, task_id: str, user: User,
) -> tuple[Task, User, int]:
    """孩子放弃:按规则退款(连续 3 次后 60% 退款)。"""
    task = await get_task(db, task_id)
    if task.family_id != user.family_id:
        raise PermissionDeniedError("只能操作自己家庭的任务")
    if not _is_adventurer(user):
        raise PermissionDeniedError("只有 ADVENTURER 可以放弃任务")
    if task.assignee_id != user.id:
        raise PermissionDeniedError("你不是该任务的接取人")
    if task.status != TaskStatus.IN_PROGRESS:
        raise ConflictError(f"当前状态 {_enum_value(task.status)},无法放弃")

    deposit = task.time_deposit or 10
    refund = coin_service.calculate_refund(deposit, user.daily_abandon_count)
    user.time_coins += refund
    await coin_service.record_transaction(
        db,
        user=user,
        type=CoinTransactionType.TASK_REFUND,
        amount=refund,
        task_id=task.id,
        note="放弃任务退还押金",
    )
    penalty = deposit - refund
    if penalty > 0:
        await coin_service.record_transaction(
            db,
            user=user,
            type=CoinTransactionType.ABANDON_PENALTY,
            amount=-penalty,
            task_id=task.id,
            note="连续放弃任务惩罚",
        )
    user.daily_abandon_count += 1

    task.status = TaskStatus.AVAILABLE
    task.assignee_id = None
    task.started_at = None

    await db.commit()
    await db.refresh(task)
    await db.refresh(user)
    return task, user, refund


async def delete_task(db: AsyncSession, *, task_id: str, family_id: str | None = None) -> None:
    t = await get_task(db, task_id)
    if family_id is not None and t.family_id != family_id:
        raise PermissionDeniedError("只能删除自己家庭的任务")
    await db.delete(t)
    await db.commit()
