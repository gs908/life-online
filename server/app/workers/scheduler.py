"""
定时任务调度器(APScheduler)。

每日 00:05 跑 daily_reset:
    遍历所有 Adventurer 档案,若 last_login_date != today,
    按家庭 ScnTimeConfig 重置 time_coin_balance 与 daily_abandon_count。
"""
from __future__ import annotations

import logging
from datetime import date

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from app.common.db.session import AsyncSessionLocal
from app.models.sys_child import SysChild
from app.services import coin_service

log = logging.getLogger(__name__)


async def daily_reset_job() -> None:
    """每日 00:05 触发:全员配额重置。"""
    today = date.today()
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


def build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")
    scheduler.add_job(
        daily_reset_job,
        CronTrigger(hour=0, minute=5),
        id="daily_reset",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    return scheduler
