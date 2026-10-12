"""
定时任务调度器(APScheduler)。

每日 00:05 跑 daily_reset:
    遍历所有 Adventurer 档案,若 last_login_date != today,
    按家庭 ScnTimeConfig 重置 time_coin_balance 与 daily_abandon_count。

每日 00:10 跑 generate_daily_instances(在 daily_reset 之后,docs/12 块 A):
    按模板触发规则幂等生成/顺延当日任务实例
    (见 app.services.task_generator_service)。

每 5 分钟跑 expire_overdue_tasks:
    扫描 AVAILABLE/IN_PROGRESS 且已过 expire_at 的任务实例,统一切 EXPIRED。
    AVAILABLE 直接过期(不涉及押金);IN_PROGRESS 退 50% 押金、其余 TIMEOUT_PENALTY
    扣罚并发 TASK_EXPIRED 通知(详见 app.services.task_service.expire_overdue_tasks)。

每日 00:20 跑 purge_expired_evidence(A7.3,DEV-44):
    物理删除软删(`scn_task_proof.deleted_at` / `sys_upload.deleted_at`)超过
    `upload.hard_delete_after_days`(默认 180 天)的证据 —— 对象存储文件 +
    台账行 + 证据行(详见 app.services.evidence_cleanup_service.hard_delete_expired)。
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select

from app.common.db.session import AsyncSessionLocal
from app.common.timeutil import today_bj
from app.models.sys_child import SysChild
from app.services import (
    coin_service,
    evidence_cleanup_service,
    task_generator_service,
    task_service,
)

log = logging.getLogger(__name__)


async def daily_reset_job() -> None:
    """每日 00:05 触发:全员配额重置。"""
    today = today_bj()
    log.info("daily_reset start, today=%s", today)
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(SysChild))
        children = list(result.scalars().all())
        for child in children:
            if child.last_login_date == today:
                continue
            try:
                await coin_service.reset_daily_allowance(db, child, today)
            except Exception:
                log.exception("daily_reset failed for child %s", child.id)
        await db.commit()
    log.info("daily_reset done, processed=%d", len(children))


async def generate_daily_instances_job() -> None:
    """每日 00:10 触发(daily_reset 之后):按触发规则生成/顺延当日实例。"""
    today = today_bj()
    log.info("generate_daily_instances start, today=%s", today)
    async with AsyncSessionLocal() as db:
        try:
            stats = await task_generator_service.run_generation(db, today=today)
        except Exception:
            log.exception("generate_daily_instances failed")
            return
    log.info("generate_daily_instances done, %s", stats)


async def expire_overdue_tasks_job() -> None:
    """每 5 分钟触发:过期任务统一切 EXPIRED。"""
    async with AsyncSessionLocal() as db:
        try:
            processed = await task_service.expire_overdue_tasks(db)
        except Exception:
            log.exception("expire_overdue_tasks failed")
            return
    if processed:
        log.info("expire_overdue_tasks done, processed=%d", processed)


async def purge_expired_evidence_job() -> None:
    """每日 00:20 触发:软删超保留期(默认 180 天)的证据定时真删。"""
    async with AsyncSessionLocal() as db:
        try:
            await evidence_cleanup_service.hard_delete_expired(db)
        except Exception:
            log.exception("purge_expired_evidence failed")


def build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")
    scheduler.add_job(
        daily_reset_job,
        CronTrigger(hour=0, minute=5),
        id="daily_reset",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        generate_daily_instances_job,
        CronTrigger(hour=0, minute=10),
        id="generate_daily_instances",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        expire_overdue_tasks_job,
        IntervalTrigger(minutes=5),
        id="expire_overdue_tasks",
        replace_existing=True,
        misfire_grace_time=300,
    )
    scheduler.add_job(
        purge_expired_evidence_job,
        CronTrigger(hour=0, minute=20),
        id="purge_expired_evidence",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    return scheduler
