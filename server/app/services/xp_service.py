"""XP 服务:评级倍数、时效加成、升级判定。"""
from __future__ import annotations

from datetime import datetime, time

from app.models.sys_child import SysChild


def xp_needed_for_level(level: int) -> int:
    """升级所需 XP(简化:每级固定 1000,后续可改为指数曲线)。"""
    return max(level, 1) * 1000


def calculate_rating_multiplier(rating: int) -> float:
    if rating == 5:
        return 1.2
    if rating == 4:
        return 1.1
    if rating < 3:
        return 0.8
    return 1.0


def calculate_xp(base_xp: int, *, rating: int | None = None,
                 started_at: datetime | None = None,
                 required_start_time: time | None = None,
                 now: datetime | None = None) -> int:
    """计算最终获得 XP(应用所有加成)。"""
    now = now or datetime.now()
    mult = 1.0
    if rating is not None:
        mult *= calculate_rating_multiplier(rating)
    if required_start_time is not None:
        deadline = now.replace(hour=required_start_time.hour,
                               minute=required_start_time.minute,
                               second=0, microsecond=0)
        if now > deadline:
            mult *= 0.8
    if started_at is not None:
        elapsed_min = (now - started_at).total_seconds() / 60
        if elapsed_min < 60:
            mult *= 1.1
    return int(round(base_xp * mult))


def apply_xp_and_level(child: SysChild, xp_gained: int) -> dict:
    """给孩子加 XP,处理升级。返回升级信息。"""
    child.xp += xp_gained
    leveled_up = False
    while child.xp >= xp_needed_for_level(child.level):
        child.xp -= xp_needed_for_level(child.level)
        child.level += 1
        leveled_up = True
    return {
        "leveled_up": leveled_up,
        "new_level": child.level,
        "final_xp": child.xp,
    }
