"""时间币服务:每日配额、押金、退款、放弃惩罚。"""
from __future__ import annotations

from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.common.exceptions import NotFoundError, PermissionDeniedError, ValidationError
from app.common.timeutil import today_bj
from app.config import DepositSection, DepositTypeRange, settings
from app.models.enums import CoinTransactionType, TaskType
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
    """放弃任务时的退款金额(连续 abandon_full_refund_limit 次后按比例退)。"""
    cfg = settings.deposit
    if abandon_count_today >= cfg.abandon_full_refund_limit:
        return int(deposit * cfg.abandon_penalty_refund_ratio)
    return deposit


def calculate_timeout_refund(deposit: int) -> int:
    """限时任务已接取(IN_PROGRESS)超时:按 timeout_refund_ratio 退押金,其余为扣罚。"""
    return int(deposit * settings.deposit.timeout_refund_ratio)


def _type_key(task_type: TaskType | str) -> str:
    return task_type.value if hasattr(task_type, "value") else str(task_type)


def _range_for(task_type: TaskType | str, cfg: DepositSection) -> DepositTypeRange:
    key = _type_key(task_type)
    rng = cfg.by_type.get(key)
    if rng is None:
        raise ValidationError(f"未知任务类型 {key!r},无法解析押金")
    return rng


def deposit_cap(daily_allowance: int, cfg: DepositSection | None = None) -> int:
    """押金上限:当日配额 × allowance_cap_ratio(避免孩子永远接不了任务)。"""
    cfg = cfg or settings.deposit
    return int(daily_allowance * cfg.allowance_cap_ratio)


def compute_deposit_detail(
    *,
    task_type: TaskType | str,
    estimated_minutes: int | None = None,
    explicit_deposit: int | None = None,
    daily_allowance: int,
    cfg: DepositSection | None = None,
) -> tuple[int, bool]:
    """押金解析的纯计算部分(不碰 DB,便于单测与预览接口复用)。

    规则见 `DepositSection` docstring:显式值优先 -> 耗时驱动 -> 类型 min/max
    clamp -> 当日配额比例封顶。难度不在参数里:难度只影响 XP,不影响押金。
    耗时乘数结果**四舍五入**(HALF_UP,`int(x + 0.5)`),不用 `round()`
    (银行家舍入会让奇数默认值 x 0.5 出现 12.5 -> 12 这类与直觉相反的下取整)。

    返回 `(解析后的押金, 是否被配额封顶截断)`;恰好等于上限但非截断时为 False。
    """
    cfg = cfg or settings.deposit
    rng = _range_for(task_type, cfg)

    if explicit_deposit is not None:
        if explicit_deposit < 0:
            raise ValidationError("time_deposit 不能为负")
        value = explicit_deposit
    else:
        base = rng.default
        if estimated_minutes is not None and estimated_minutes > 0:
            ratio = max(0.5, min(2.0, estimated_minutes / cfg.reference_minutes))
            value = int(base * ratio + 0.5)  # 四舍五入(HALF_UP)
        else:
            value = base

    value = rng.clamp(value)
    cap = deposit_cap(daily_allowance, cfg)
    capped = value > cap
    return (cap if capped else value), capped


def compute_deposit(
    *,
    task_type: TaskType | str,
    estimated_minutes: int | None = None,
    explicit_deposit: int | None = None,
    daily_allowance: int,
    cfg: DepositSection | None = None,
) -> int:
    """`compute_deposit_detail` 的便捷封装,只取解析后的押金。"""
    deposit, _capped = compute_deposit_detail(
        task_type=task_type,
        estimated_minutes=estimated_minutes,
        explicit_deposit=explicit_deposit,
        daily_allowance=daily_allowance,
        cfg=cfg,
    )
    return deposit


async def resolve_deposit(
    db: AsyncSession,
    *,
    family_id: str,
    task_type: TaskType | str,
    estimated_minutes: int | None = None,
    explicit_deposit: int | None = None,
    day: date | None = None,
    cfg: DepositSection | None = None,
) -> int:
    """创建任务模板/实例时解析押金并落库(替代 `time_deposit or 10` 兜底)。"""
    day = day or today_bj()
    allowance = await compute_daily_allowance(db, family_id, day)
    return compute_deposit(
        task_type=task_type,
        estimated_minutes=estimated_minutes,
        explicit_deposit=explicit_deposit,
        daily_allowance=allowance,
        cfg=cfg,
    )


def calculate_deposit_fee(time_deposit: int) -> int:
    """接取任务时的押金(目前直接等于 time_deposit,创建时已由 resolve_deposit 解析落库)。"""
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
