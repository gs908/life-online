"""
XP 服务:评级倍数、时效加成、速度加成、升级判定。

- 升级所需 XP 采用指数曲线,公式集中在 `XpSection`(`app.config.xp`)便于调参。
- 所有倍率(星级 / 挑战 / 隐藏 / 链末 / 时效 / 速度)都通过配置注入,
  本服务不直接 hard-code 魔法数。
- 计算 `final_xp` 时,**不**做向下取整以外的二次封顶;调用方在 UI 层做展示。
"""
from __future__ import annotations

from datetime import datetime, time

from app.config import settings
from app.config import XpSection
from app.models.sys_child import SysChild


# ---- 升级曲线 -----------------------------------------------------------

def xp_required_for_level(
    level: int, *, base_xp: int | None = None, growth: float | None = None
) -> int:
    """
    从 Lv L 升到 Lv L+1 所需 XP。

    公式: `base_xp * growth ** (L - 1)`,默认 base=200, growth=1.5。

    样例(默认配置):
        L=1  -> 200
        L=2  -> 300
        L=3  -> 450
        L=4  -> 675
        L=5  -> 1013
        L=10 -> 7680
        L=15 -> 58262
    """
    cfg_base = base_xp if base_xp is not None else settings.xp.base_xp
    cfg_growth = growth if growth is not None else settings.xp.growth
    if level < 1:
        return cfg_base
    return int(round(cfg_base * (cfg_growth ** (level - 1))))


# ---- 单任务 XP 计算 ------------------------------------------------------

def calculate_rating_multiplier(rating: int | None, cfg: XpSection) -> float:
    """1-5 星 -> 倍率,缺省按 3 星 1.0。"""
    if rating is None:
        rating = 3
    rating = max(1, min(5, int(rating)))
    return float(cfg.rating_multiplier.get(rating, 1.0))


def calculate_xp(
    base_xp: int,
    *,
    rating: int | None = None,
    started_at: datetime | None = None,
    submitted_at: datetime | None = None,
    required_start_time: time | None = None,
    is_challenge: bool = False,
    is_hidden: bool = False,
    chain_index: int | None = None,
    chain_total: int | None = None,
    now: datetime | None = None,
    cfg: XpSection | None = None,
) -> int:
    """
    最终 XP = base * rating_mul * timing_mul * speed_mul * type_mul * chain_mul
    """
    cfg = cfg or settings.xp
    now = now or datetime.utcnow()
    mul = 1.0

    # 1) 星级
    mul *= calculate_rating_multiplier(rating, cfg)

    # 2) 时效:限时任务在 required_start_time 之前完成 -> bonus,之后 -> penalty;非限时 -> 1.0
    if required_start_time is not None:
        deadline = now.replace(
            hour=required_start_time.hour,
            minute=required_start_time.minute,
            second=0,
            microsecond=0,
        )
        mul *= cfg.timing_bonus if now <= deadline else cfg.timing_penalty

    # 3) 速度:窗口内完成 -> bonus;窗口外或缺失 -> 1.0
    if started_at is not None and submitted_at is not None:
        elapsed_min = (submitted_at - started_at).total_seconds() / 60
        if 0 < elapsed_min <= cfg.speed_window_minutes:
            mul *= cfg.speed_bonus

    # 4) 任务类型加成
    if is_challenge:
        mul *= cfg.challenge_bonus
    if is_hidden:
        mul *= cfg.hidden_bonus

    # 5) 连环任务链末加成
    if (
        chain_index is not None
        and chain_total is not None
        and chain_index > 0
        and chain_total > 0
        and chain_index == chain_total
    ):
        mul *= cfg.chain_final_bonus

    return int(round(base_xp * mul))


# ---- 升级判定 -----------------------------------------------------------

def apply_xp_and_level(
    child: SysChild, xp_gained: int, *, cfg: XpSection | None = None
) -> dict:
    """
    给孩子加 XP,处理升级(可能跨多级)。

    返回: { leveled_up, levels_gained, new_level, current_xp, next_level_xp_required }
    """
    cfg = cfg or settings.xp
    child.xp += xp_gained
    levels_gained = 0
    while child.xp >= xp_required_for_level(child.level, base_xp=cfg.base_xp, growth=cfg.growth):
        child.xp -= xp_required_for_level(child.level, base_xp=cfg.base_xp, growth=cfg.growth)
        child.level += 1
        levels_gained += 1
    return {
        "leveled_up": levels_gained > 0,
        "levels_gained": levels_gained,
        "new_level": child.level,
        "current_xp": child.xp,
        "next_level_xp_required": xp_required_for_level(
            child.level, base_xp=cfg.base_xp, growth=cfg.growth
        ),
    }
