"""时间币服务:每日配额、押金、退款、放弃惩罚。"""
from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.common.exceptions import NotFoundError, ValidationError
from app.models.coin_transaction import CoinTransaction
from app.models.enums import CoinTransactionType
from app.models.time_config import TimeConfig
from app.models.user import User

if TYPE_CHECKING:
    from app.models.task import Task


async def record_transaction(
    db: AsyncSession,
    *,
    user: User,
    type: CoinTransactionType,
    amount: int,
    task_id: str | None = None,
    note: str | None = None,
) -> CoinTransaction:
    record = CoinTransaction(
        family_id=user.family_id,
        user_id=user.id,
        task_id=task_id,
        type=type,
        amount=amount,
        balance_after=user.time_coins,
        note=note,
    )
    db.add(record)
    return record


async def get_or_create_time_config(db: AsyncSession, family_id: str) -> TimeConfig:
    tc = (
        await db.execute(
            select(TimeConfig)
            .where(TimeConfig.family_id == family_id)
            .options(selectinload(TimeConfig.exceptions))
        )
    ).scalar_one_or_none()
    if tc:
        return tc
    tc = TimeConfig(family_id=family_id, default_daily_allowance=100)
    db.add(tc)
    await db.flush()
    return tc


async def compute_daily_allowance(db: AsyncSession, family_id: str, day: date) -> int:
    tc = await get_or_create_time_config(db, family_id)
    dow = day.weekday()  # Mon=0..Sun=6,与表里 0=Sun 不同
    # 转换为表里 day_of_week 语义(0=Sun..6=Sat)
    table_dow = (dow + 1) % 7
    for ex in tc.exceptions:
        if ex.day_of_week == table_dow:
            return ex.coin_amount
    return tc.default_daily_allowance


async def reset_daily_allowance(db: AsyncSession, user: User, today: date) -> int:
    """每日首次登录时重置。返回重置后的配额。"""
    allowance = await compute_daily_allowance(db, user.family_id, today)
    delta = allowance - user.time_coins
    user.time_coins = allowance
    user.daily_abandon_count = 0
    user.last_login_date = today
    await record_transaction(
        db,
        user=user,
        type=CoinTransactionType.DAILY_RESET,
        amount=delta,
        note="每日时间币重置",
    )
    return allowance


def calculate_refund(deposit: int, abandon_count_today: int) -> int:
    """放弃任务时的退款金额。

    - abandon_count_today >= 3 时仅退 60%(40% 惩罚)
    - 否则全退
    """
    if abandon_count_today >= 3:
        return int(deposit * 0.6)
    return deposit


def calculate_deposit_fee(time_deposit: int) -> int:
    """接取任务时的押金(目前直接等于 time_deposit)。"""
    if time_deposit < 0:
        raise ValidationError("time_deposit 不能为负")
    return time_deposit


def has_sufficient_coins(user: User, required: int) -> bool:
    return user.time_coins >= required


async def ensure_user(db: AsyncSession, user_id: str) -> User:
    u = await db.get(User, user_id)
    if not u:
        raise NotFoundError(f"用户 {user_id} 不存在")
    return u


async def adjust_coins(
    db: AsyncSession,
    *,
    user_id: str,
    family_id: str,
    amount: int,
    note: str | None = None,
) -> tuple[User, CoinTransaction]:
    user = await ensure_user(db, user_id)
    if user.family_id != family_id:
        from app.common.exceptions import PermissionDeniedError
        raise PermissionDeniedError("只能调整自己家庭成员的时间币")
    new_balance = user.time_coins + amount
    if new_balance < 0:
        raise ValidationError("时间币余额不能为负")
    user.time_coins = new_balance
    tx = await record_transaction(
        db,
        user=user,
        type=CoinTransactionType.MANUAL_ADJUST,
        amount=amount,
        note=note,
    )
    await db.commit()
    await db.refresh(user)
    await db.refresh(tx)
    return user, tx


async def list_transactions(
    db: AsyncSession,
    *,
    family_id: str,
    user_id: str | None = None,
    offset: int = 0,
    limit: int = 20,
) -> tuple[list[CoinTransaction], int]:
    from sqlalchemy import func

    stmt = select(CoinTransaction).where(CoinTransaction.family_id == family_id)
    if user_id is not None:
        stmt = stmt.where(CoinTransaction.user_id == user_id)
    total = int((await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one())
    items = list((await db.execute(
        stmt.order_by(CoinTransaction.created_at.desc()).offset(offset).limit(limit)
    )).scalars().all())
    return items, total
