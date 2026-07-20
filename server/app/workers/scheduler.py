"""
定时任务调度器(APScheduler)。

启动入口在 main.py 的 lifespan 中:
    scheduler.start()

每日 00:05 跑 daily_reset:
    遍历所有 Adventurer,若 last_login_date != today,
    按家庭 TimeConfig 重置 time_coins 与 daily_abandon_count。
"""
from __future__ import annotations

import logging
from datetime import date

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from app.common.db.session import AsyncSessionLocal
from app.models.enums import UserRole
from app.models.user import User
from app.services import coin_service

log = logging.getLogger(__name__)


async def daily_reset_job() -> None:
    """每日 00:05 触发:全员配额重置。"""
    today = date.today()
    log.info("daily_reset start, today=%s", today)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User).where(User.role == UserRole.ADVENTURER.value)
        )
        users = list(result.scalars().all())
        for u in users:
            if u.last_login_date == today:
                continue
            try:
                await coin_service.reset_daily_allowance(db, u, today)
            except Exception:
                log.exception("daily_reset failed for user %s", u.id)
        await db.commit()
    log.info("daily_reset done, processed=%d", len(users))


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
