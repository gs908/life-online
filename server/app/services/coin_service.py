"""时间币服务:每日配额、押金、退款、放弃惩罚。"""
from __future__ import annotations

from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.common.exceptions import NotFoundError, PermissionDeniedError, ValidationError
from app.models.enums import CoinTransactionType
from app.models.scn_time_coin_log import ScnTimeCoinLog
from app.models.scn_time_config import ScnTimeConfig
from app.models.sys_child import SysChild


async def record_transaction(
    db: AsyncSession,
    *,
    child: SysChild,
    type: CoinTransactionType,
    amount: int,
    task_instance_id: str | None = None,
    note: str | None = None,
) -> ScnTimeCoinLog:
    record = ScnTimeCoinLog(
        family_id=child.family_id,
        child_id=child.id,
        season_id=child.current_season_id,
        task_instance_id=task_instance_id,
        type=type,
        amount=amount,
        balance_after=child.time_coin_balance,
        note=note,
    )
    db.add(record)
    return record


async def get_or_create_time_config(db: AsyncSession, family_id: str) -> ScnTimeConfig:
    tc = (
        await db.execute(
            select(ScnTimeConfig)
            .where(ScnTimeConfig.family_id == family_id)
            .options(selectinload(ScnTimeConfig.exceptions))
        )
    ).scalar_one_or_none()
    if tc:
        return tc
    tc = ScnTimeConfig(family_id=family_id, default_daily_allowance=100)
    db.add(tc)
    await db.flush()
    return tc


async def compute_daily_allowance(db: AsyncSession, family_id: str, day: date) -> int:
    tc = await get_or_create_time_config(db, family_id)
    dow = day.weekday()  # Mon=0..Sun=6,与表里 0=Sun 不同
    table_dow = (dow + 1) % 7
    for ex in tc.exceptions:
        if ex.day_of_week == table_dow:
            return ex.coin_amount
    return tc.default_daily_allowance


async def reset_daily_allowance(db: AsyncSession, child: SysChild, today: date) -> int:
    """每日首次登录时重置。返回重置后的配额。"""
    allowance = await compute_daily_allowance(db, child.family_id, today)
    delta = allowance - child.time_coin_balance
    child.time_coin_balance = allowance
    child.daily_abandon_count = 0
    child.last_login_date = today
    await record_transaction(
        db,
        child=child,
        type=CoinTransactionType.DAILY_RESET,
        amount=delta,
        note="每日时间币重置",
    )
    return allowance


def calculate_refund(deposit: int, abandon_count_today: int) -> int:
    """放弃任务时的退款金额。"""
    if abandon_count_today >= 3:
        return int(deposit * 0.6)
    return deposit


def calculate_deposit_fee(time_deposit: int) -> int:
    """接取任务时的押金(目前直接等于 time_deposit)。"""
    if time_deposit < 0:
        raise ValidationError("time_deposit 不能为负")
    return time_deposit


def has_sufficient_coins(child: SysChild, required: int) -> bool:
    return child.time_coin_balance >= required


async def ensure_child(db: AsyncSession, child_id: str) -> SysChild:
    child = await db.get(SysChild, child_id)
    if child:
        return child
    child = (
        await db.execute(select(SysChild).where(SysChild.account_id == child_id))
    ).scalar_one_or_none()
    if not child:
        raise NotFoundError(f"孩子 {child_id} 不存在")
    return child


async def adjust_coins(
    db: AsyncSession,
    *,
    user_id: str,
    family_id: str,
    amount: int,
    note: str | None = None,
) -> tuple[SysChild, ScnTimeCoinLog]:
    child = await ensure_child(db, user_id)
    if child.family_id != family_id:
        raise PermissionDeniedError("只能调整自己家庭成员的时间币")
    new_balance = child.time_coin_balance + amount
    if new_balance < 0:
        raise ValidationError("时间币余额不能为负")
    child.time_coin_balance = new_balance
    tx = await record_transaction(
        db,
        child=child,
        type=CoinTransactionType.MANUAL_ADJUST,
        amount=amount,
        note=note,
    )
    await db.commit()
    await db.refresh(child)
    await db.refresh(tx)
    return child, tx


async def list_transactions(
    db: AsyncSession,
    *,
    family_id: str,
    user_id: str | None = None,
    offset: int = 0,
    limit: int = 20,
) -> tuple[list[ScnTimeCoinLog], int]:
    stmt = select(ScnTimeCoinLog).where(ScnTimeCoinLog.family_id == family_id)
    if user_id is not None:
        child = await ensure_child(db, user_id)
        stmt = stmt.where(
            or_(ScnTimeCoinLog.child_id == child.id, ScnTimeCoinLog.child_id == user_id)
        )
    total = int((await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one())
    items = list((await db.execute(
        stmt.order_by(ScnTimeCoinLog.created_at.desc()).offset(offset).limit(limit)
    )).scalars().all())
    return items, total
