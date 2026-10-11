"""CHAIN 递进串行任务服务(DEV-36 块 F)。

链的结构语义在本模块:
- 模板共享 `chain_key`,按 `chain_order`(1-based)排序,创建时校验
  (chain_key 必填、chain_total >= 2、family 内 chain_order 不重复)。
- 实例化时把 `chain_order`/`chain_total` 快照到实例的 `chain_index`/`chain_total`,
  审批通过时传给 `xp_service.calculate_xp` 做链末加成判定。

与 DEV-35(块 A+B:任务生成器与实例化池)的接线约定:

- 链的「投放 / 链内步骤顺延 / 过期重做」池语义属于 DEV-35 的生成器,
  本模块**不**实现池规则,只提供 `spawn_next_chain_step` 作为
  "第 N 步 COMPLETED -> 生成第 N+1 步"的唯一接合点。
  当前实现是池合入前的最小可用版:按步序找到下一模板即建一条 AVAILABLE
  实例;DEV-35 合入后,只需把该函数内部替换为对生成器池的调用
  (传入链上下文),task_service 等调用方一行不改。
- 中断与续做(已定稿):链内某步 abandon 或超时**不回退整条链**——
  已完成步骤保持 COMPLETED,当前步骤按现有单人状态机流转
  (abandon -> AVAILABLE 可重做;EXPIRED 后的重做路径随 DEV-35 池规则落地)。
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exceptions import ConflictError, ValidationError
from app.common.timeutil import utcnow
from app.models.enums import TaskStatus, TaskType
from app.models.scn_task_instance import ScnTaskInstance
from app.models.scn_task_template import ScnTaskTemplate


async def validate_chain_template(
    db: AsyncSession,
    *,
    family_id: str,
    task_type: TaskType,
    chain_key: str | None,
    chain_order: int,
    chain_total: int,
    exclude_template_id: str | None = None,
) -> None:
    """创建/更新模板时的 CHAIN 字段校验。

    - chain_* 字段只有 CHAIN 类型可用;
    - CHAIN 必须给 chain_key,且 1 <= chain_order <= chain_total,chain_total >= 2
      (单步链恒命中链末加成,没有意义,直接禁止);
    - 同家庭同链的 chain_order 不允许重复。
    """
    if task_type != TaskType.CHAIN:
        if chain_key is not None:
            raise ValidationError("chain_key 等链式字段仅 CHAIN 类型任务可用")
        return

    if not chain_key:
        raise ValidationError("CHAIN 任务必须指定 chain_key")
    if chain_total < 2:
        raise ValidationError("CHAIN 任务至少两步(chain_total >= 2)")
    if not (1 <= chain_order <= chain_total):
        raise ValidationError("chain_order 必须在 1..chain_total 之间")

    stmt = select(ScnTaskTemplate).where(
        ScnTaskTemplate.family_id == family_id,
        ScnTaskTemplate.chain_key == chain_key,
        ScnTaskTemplate.chain_order == chain_order,
    )
    if exclude_template_id is not None:
        stmt = stmt.where(ScnTaskTemplate.id != exclude_template_id)
    dup = (await db.execute(stmt)).scalar_one_or_none()
    if dup is not None:
        raise ConflictError(
            f"链 {chain_key} 的第 {chain_order} 步已存在(title={dup.title!r})"
        )


async def spawn_next_chain_step(
    db: AsyncSession, completed: ScnTaskInstance
) -> ScnTaskInstance | None:
    """第 N 步 COMPLETED 后生成第 N+1 步 —— DEV-35 接合点(本函数是唯一接线处)。

    幂等:同家庭同链同步序已存在非终态实例(EXPIRED 除外)则不再生成,
    防止审批重放/并发审批把同一步投放两次。

    池合入前的最小语义:
    - 下一实例状态 AVAILABLE,继承家庭/赛季/创建人/目标孩子;
    - expire_at = 完成时刻 + 下一模板 estimated_minutes(若配置),
      否则为空(交给池的默认窗口规则);
    - deadline 同步使用同一窗口,保持两字段一致。
    """
    template = completed.template
    if template is None or not template.chain_key:
        return None

    index = completed.chain_index or template.chain_order
    total = completed.chain_total or template.chain_total
    if index >= total:
        return None  # 链末,无下一步

    next_template = (
        await db.execute(
            select(ScnTaskTemplate).where(
                ScnTaskTemplate.family_id == completed.family_id,
                ScnTaskTemplate.chain_key == template.chain_key,
                ScnTaskTemplate.chain_order == index + 1,
                ScnTaskTemplate.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if next_template is None:
        # 链定义不完整(后续步骤模板尚未创建):不视为错误,链在此暂停;
        # 家长补建步骤模板后, DEV-35 的池会负责按断点继续投放。
        return None

    # 幂等防重:非终态的同序号实例已存在则跳过
    dup_stmt = (
        select(ScnTaskInstance)
        .join(ScnTaskTemplate, ScnTaskInstance.template_id == ScnTaskTemplate.id)
        .where(
            ScnTaskInstance.family_id == completed.family_id,
            ScnTaskTemplate.chain_key == template.chain_key,
            ScnTaskInstance.chain_index == index + 1,
            ScnTaskInstance.status != TaskStatus.EXPIRED,
        )
    )
    if completed.target_child_id is not None:
        dup_stmt = dup_stmt.where(
            ScnTaskInstance.target_child_id == completed.target_child_id
        )
    else:
        dup_stmt = dup_stmt.where(ScnTaskInstance.target_child_id.is_(None))
    dup = (await db.execute(dup_stmt)).scalar_one_or_none()
    if dup is not None:
        return None

    now = utcnow()
    expire_at = (
        now + timedelta(minutes=next_template.estimated_minutes)
        if next_template.estimated_minutes
        else None
    )
    next_instance = ScnTaskInstance(
        family_id=completed.family_id,
        season_id=completed.season_id,
        template_id=next_template.id,
        creator_account_id=completed.creator_account_id,
        target_child_id=completed.target_child_id,
        title=next_template.title,
        description=next_template.description,
        lore_snippet=next_template.lore_snippet,
        xp_reward=next_template.xp_reward,
        status=TaskStatus.AVAILABLE,
        deadline=expire_at,
        expire_at=expire_at,
        time_deposit=next_template.time_deposit,
        chain_index=index + 1,
        chain_total=total,
    )
    db.add(next_instance)
    await db.flush()
    return next_instance
