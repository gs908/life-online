"""COOP 多参与者协作任务服务(DEV-36 块 F)。

均摊规则(docs/04 §4 / §8:分摊默认均摊,后续可配):
- 押金:实例 `time_deposit` 是**总额**,在「持有钱包的已确认参与者」(孩子)间
  均摊;家长参与者(PARENT)没有时间币账户,不占份额。
- XP:审批后的最终 XP 同样在孩子参与者间均摊;家长参与者不获得 XP。

动态均摊(rebalance)模型:
- 主接取人 start 时独自承担全额(此时 n=1);
- 每个孩子 join 时按当前人数重新 `split_evenly`,老参与者即时退还差额,
  新参与者只付新份额——任意时刻「已收押金之和 == 总额」严格成立;
- 审批/放弃/过期按每人 `deposit_share` 结算。

与 DEV-34(块 C,DepositSection/resolve_deposit)的接线约定:
`split_evenly` / `per_participant_shares` 是押金拆分的唯一入口。块 C 合入后,
只需把这两个函数改为委托 `resolve_deposit`(读 DepositSection 的分摊配置),
调用方与结算逻辑不变。
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.common.exceptions import ConflictError, NotFoundError, PermissionDeniedError, ValidationError
from app.common.timeutil import utcnow
from app.models.enums import (
    CoinTransactionType,
    TaskParticipantRole,
    TaskStatus,
    TaskType,
    UserRole,
)
from app.models.scn_task_instance import ScnTaskInstance
from app.models.scn_task_participant import ScnTaskParticipant
from app.models.sys_account import SysAccount
from app.models.sys_child import SysChild
from app.services import coin_service


def split_evenly(total: int, n: int) -> list[int]:
    """把 total 均摊给 n 份,余数分给前 (total % n) 份;和恒等于 total。

    >>> split_evenly(20, 2)
    [10, 10]
    >>> split_evenly(5, 2)
    [3, 2]
    >>> split_evenly(3, 5)
    [1, 1, 1, 0, 0]
    """
    if n <= 0:
        return []
    base, rem = divmod(max(total, 0), n)
    return [base + 1 if i < rem else base for i in range(n)]


def per_participant_shares(total: int, participants: int) -> list[int]:
    """按参与者人数均摊押金 —— DEV-34 `resolve_deposit` 的接合点。

    块 C 合入后改为: 读 DepositSection 配置(分摊模式/上下限/步进)并调用
    resolve_deposit 得到每人份额;当前为默认的整数均摊实现。
    """
    return split_evenly(total, participants)


def is_coop(task: ScnTaskInstance) -> bool:
    template = task.template
    return template is not None and template.type == TaskType.COOP


def wallet_participants(task: ScnTaskInstance) -> list[ScnTaskParticipant]:
    """已确认的、有钱包的参与者(孩子),按加入顺序(OWNER 最先)。"""
    return [
        p for p in task.participants
        if p.child_id is not None and p.confirmed_at is not None
    ]


async def _lock_task_for_join(db: AsyncSession, task_id: str) -> ScnTaskInstance:
    """行锁取任务实例(MR #10 审查 🔴 修复)。

    join 的重摊是"读参与者 → 算份额 → 逐行退款/扣款"的读-改-写:
    两个孩子并发 join 会都读到 owner 独占全额、都按 n=2 重摊、都给 owner
    退差额,打破"已收之和 == 总额"的金额守恒。对实例行 FOR UPDATE 后,
    join 与 settle(approve/abandon/expire,见 task_service.get_task_for_update)
    在同一把实例行锁上互斥(先例: DEV-20 `family_service._lock_invite_or_raise`)。
    """
    task = (
        await db.execute(
            select(ScnTaskInstance)
            .where(ScnTaskInstance.id == task_id)
            .with_for_update()
            .options(
                selectinload(ScnTaskInstance.template),
                selectinload(ScnTaskInstance.participants),
            )
        )
    ).scalar_one_or_none()
    if not task:
        raise NotFoundError(f"任务 {task_id} 不存在")
    return task


async def join_task(db: AsyncSession, *, task_id: str, user: SysAccount) -> ScnTaskInstance:
    """孩子/家长加入 COOP 任务。

    - 孩子(MEMBER):按当前人数重新均摊押金,老参与者退差额,本人扣新份额;
    - 家长(PARENT,亲子协作):登记参与,不动钱包。
    仅 IN_PROGRESS 可加入(主接取人 start 之后、提交之前)。
    """
    role_value = user.role.value if hasattr(user.role, "value") else str(user.role)
    task = await _lock_task_for_join(db, task_id)
    status_value = task.status.value if hasattr(task.status, "value") else str(task.status)
    if task.family_id != user.family_id:
        raise PermissionDeniedError("只能加入自己家庭的任务")
    if not is_coop(task):
        raise ValidationError("只有 COOP 协作任务支持加入")
    if status_value != TaskStatus.IN_PROGRESS.value:
        raise ConflictError("任务当前状态不可加入(需主接取人先接取)")

    if any(p.account_id == user.id for p in task.participants):
        raise ConflictError("你已是该任务的参与者")

    now = utcnow()
    if role_value == UserRole.GUILD_MASTER.value:
        # 亲子协作:家长作为一方参与者登记,无钱包、不占押金/XP 份额
        db.add(ScnTaskParticipant(
            task_instance_id=task.id,
            account_id=user.id,
            child_id=None,
            role=TaskParticipantRole.PARENT,
            confirmed_at=now,
            deposit_share=0,
        ))
        await db.commit()
        await db.refresh(task)
        return task

    if role_value != UserRole.ADVENTURER.value:
        raise ValidationError("只有孩子或家长可以加入协作任务")

    child = await db.get(SysChild, user.id)
    if child is None:
        child = (
            await db.execute(select(SysChild).where(SysChild.account_id == user.id))
        ).scalar_one_or_none()
    if not child:
        raise NotFoundError(f"孩子 {user.id} 不存在")

    if any(p.child_id == child.id for p in task.participants):
        raise ConflictError("你已是该任务的参与者")

    wallets = wallet_participants(task)
    total_deposit = task.time_deposit if task.time_deposit is not None else 10
    shares = per_participant_shares(total_deposit, len(wallets) + 1)
    new_share = shares[-1]

    if not coin_service.has_sufficient_coins(child, new_share):
        raise ValidationError(
            f"时间币不足,需要 {new_share},当前 {child.time_coin_balance}"
        )

    # 老参与者退差额(重新均摊后每人份额只会变小或不变)
    for i, p in enumerate(wallets):
        refund = p.deposit_share - shares[i]
        p.deposit_share = shares[i]
        if refund > 0:
            old_child = await db.get(SysChild, p.child_id)
            if old_child is not None:
                old_child.time_coin_balance += refund
                await coin_service.record_transaction(
                    db,
                    child=old_child,
                    type=CoinTransactionType.TASK_REFUND,
                    amount=refund,
                    task_instance_id=task.id,
                    note="协作者加入,押金重新均摊退还差额",
                )

    child.time_coin_balance -= new_share
    await coin_service.record_transaction(
        db,
        child=child,
        type=CoinTransactionType.TASK_DEPOSIT,
        amount=-new_share,
        task_instance_id=task.id,
        note="加入协作任务扣除押金份额",
    )
    db.add(ScnTaskParticipant(
        task_instance_id=task.id,
        account_id=user.id,
        child_id=child.id,
        role=TaskParticipantRole.MEMBER,
        confirmed_at=now,
        deposit_share=new_share,
    ))

    await db.commit()
    await db.refresh(task)
    return task
