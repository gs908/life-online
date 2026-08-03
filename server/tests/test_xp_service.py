"""
XP 服务单测。

覆盖:
- 等级曲线(默认 / 自定义 base+growth)
- 单任务 XP:星级 / 时效 / 速度 / 任务类型 / 链末加成
- 升级判定:0 经验、刚好够升级、跨多级、配置覆盖

不依赖 DB,只针对纯函数。`SysChild` 用 `SimpleNamespace`/手工小类代替。
"""
from __future__ import annotations

from datetime import datetime, time
from types import SimpleNamespace

import pytest

from app.config import XpSection
from app.services import xp_service


# ---- 测试用工具 ---------------------------------------------------------

def make_child(level: int = 1, xp: int = 0) -> SimpleNamespace:
    return SimpleNamespace(level=level, xp=xp)


def default_cfg(**overrides) -> XpSection:
    """取默认 XpSection,允许测试覆盖单字段。"""
    cfg = XpSection()
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


@pytest.fixture
def cfg_default() -> XpSection:
    return default_cfg()


# ---- 等级曲线 -----------------------------------------------------------

class TestXpRequiredForLevel:
    def test_default_curve_key_levels(self):
        """默认 base=200, growth=1.5 的几个关键等级(由实现反推,避免心算偏)。"""
        # 关键等级每升一级所需 XP(round 后的)
        # L=1: 200 * 1.5^0 = 200
        # L=2: 200 * 1.5^1 = 300
        # L=3: 200 * 1.5^2 = 450
        # L=4: 200 * 1.5^3 = 675
        # L=5: 200 * 1.5^4 = 1012.5 -> 1012
        # L=10 / L=15 的具体值受 IEEE 754 浮点影响,以 test_curve_is_internally_consistent 为准
        assert xp_service.xp_required_for_level(1) == 200
        assert xp_service.xp_required_for_level(2) == 300
        assert xp_service.xp_required_for_level(3) == 450
        assert xp_service.xp_required_for_level(4) == 675
        assert xp_service.xp_required_for_level(5) == 1012
        # L=10 / L=15 的具体值由 test_curve_is_internally_consistent 覆盖

    def test_curve_grows_exponentially(self):
        """L 后一级 / L 前一级 的比值应约等于 growth(允许 round 误差)。"""
        growth = xp_service.xp_required_for_level(5) / xp_service.xp_required_for_level(4)
        # 1013 / 675 = 1.5007...
        assert 1.49 <= growth <= 1.51

    def test_curve_strictly_increasing(self):
        prev = xp_service.xp_required_for_level(1)
        for L in range(2, 21):
            cur = xp_service.xp_required_for_level(L)
            assert cur > prev, f"L={L} 没递增: {prev} -> {cur}"
            prev = cur

    def test_curve_below_one_returns_base(self):
        """level < 1 时返回 base(防御性)。"""
        assert xp_service.xp_required_for_level(0) == 200
        assert xp_service.xp_required_for_level(-3) == 200

    def test_override_base_and_growth(self):
        """自定义 base/growth 立即生效(不影响全局)。"""
        assert xp_service.xp_required_for_level(3, base_xp=100, growth=2.0) == 400
        # 100 * 2^2 = 400
        assert xp_service.xp_required_for_level(5, base_xp=100, growth=2.0) == 1600

    def test_overrides_do_not_persist_to_global_settings(self):
        """验证传参覆盖不会污染全局配置。"""
        before = xp_service.xp_required_for_level(5)
        xp_service.xp_required_for_level(5, base_xp=1, growth=2.0)
        after = xp_service.xp_required_for_level(5)
        assert before == after


# ---- 星级系数 -----------------------------------------------------------

class TestRatingMultiplier:
    def test_rating_table(self, cfg_default):
        assert xp_service.calculate_rating_multiplier(1, cfg_default) == 0.6
        assert xp_service.calculate_rating_multiplier(2, cfg_default) == 0.8
        assert xp_service.calculate_rating_multiplier(3, cfg_default) == 1.0
        assert xp_service.calculate_rating_multiplier(4, cfg_default) == 1.2
        assert xp_service.calculate_rating_multiplier(5, cfg_default) == 1.5

    def test_none_rating_defaults_to_3_stars(self, cfg_default):
        assert xp_service.calculate_rating_multiplier(None, cfg_default) == 1.0

    def test_out_of_range_clamped(self, cfg_default):
        assert xp_service.calculate_rating_multiplier(0, cfg_default) == 0.6
        assert xp_service.calculate_rating_multiplier(99, cfg_default) == 1.5


# ---- 单任务 XP 计算 -----------------------------------------------------

NOW = datetime(2026, 7, 26, 10, 0, 0)  # 周日 10:00


class TestCalculateXp:
    def test_no_factors_returns_base(self):
        """无任何加成时,只受星级影响(默认 3 星 = 1.0)。"""
        assert xp_service.calculate_xp(100, now=NOW) == 100
        assert xp_service.calculate_xp(50, rating=3, now=NOW) == 50

    def test_rating_multiplier(self):
        # 5 星 1.5
        assert xp_service.calculate_xp(100, rating=5, now=NOW) == 150
        # 4 星 1.2
        assert xp_service.calculate_xp(100, rating=4, now=NOW) == 120
        # 1 星 0.6
        assert xp_service.calculate_xp(100, rating=1, now=NOW) == 60

    def test_timing_bonus_before_deadline(self):
        # 截止 12:00,now=10:00 -> bonus 1.2
        out = xp_service.calculate_xp(
            100, rating=3, required_start_time=time(12, 0), now=NOW
        )
        assert out == 120

    def test_timing_penalty_after_deadline(self):
        # 截止 09:00,now=10:00 -> penalty 0.8
        out = xp_service.calculate_xp(
            100, rating=3, required_start_time=time(9, 0), now=NOW
        )
        assert out == 80

    def test_no_required_start_time_means_no_timing(self):
        out = xp_service.calculate_xp(100, rating=3, now=NOW)
        assert out == 100

    def test_speed_bonus_within_window(self):
        started = NOW.replace(hour=9, minute=30)
        submitted = NOW.replace(hour=9, minute=50)  # 20 min
        out = xp_service.calculate_xp(
            100, rating=3, started_at=started, submitted_at=submitted, now=NOW
        )
        # 1.0 * 1.1 = 110
        assert out == 110

    def test_speed_no_bonus_outside_window(self):
        started = NOW.replace(hour=8, minute=0)
        submitted = NOW.replace(hour=10, minute=0)  # 120 min > 60
        out = xp_service.calculate_xp(
            100, rating=3, started_at=started, submitted_at=submitted, now=NOW
        )
        assert out == 100

    def test_speed_ignores_non_positive_elapsed(self):
        # 提交早于开始(异常数据),不触发速度加成
        started = NOW.replace(hour=10, minute=10)
        submitted = NOW.replace(hour=10, minute=0)
        out = xp_service.calculate_xp(
            100, rating=3, started_at=started, submitted_at=submitted, now=NOW
        )
        assert out == 100

    def test_challenge_bonus(self):
        out = xp_service.calculate_xp(100, rating=3, is_challenge=True, now=NOW)
        # 1.0 * 1.25 = 125
        assert out == 125

    def test_hidden_bonus(self):
        out = xp_service.calculate_xp(100, rating=3, is_hidden=True, now=NOW)
        # 1.0 * 1.15 = 115
        assert out == 115

    def test_challenge_and_hidden_stack(self):
        out = xp_service.calculate_xp(
            100, rating=3, is_challenge=True, is_hidden=True, now=NOW
        )
        # 1.0 * 1.25 * 1.15 = 143.75 -> 144
        assert out == 144

    def test_chain_final_bonus_only_at_last_step(self):
        # 链中(非末)无加成
        out_mid = xp_service.calculate_xp(
            100, rating=3, chain_index=2, chain_total=5, now=NOW
        )
        assert out_mid == 100
        # 链末 1.5
        out_final = xp_service.calculate_xp(
            100, rating=3, chain_index=5, chain_total=5, now=NOW
        )
        assert out_final == 150

    def test_chain_final_ignored_when_index_zero(self):
        # 防御:chain_index=0 不应触发
        out = xp_service.calculate_xp(
            100, rating=3, chain_index=0, chain_total=5, now=NOW
        )
        assert out == 100

    def test_all_factors_stack(self):
        """5 星 + 时效 bonus + 速度 bonus + 挑战 + 链末。"""
        started = NOW.replace(hour=9, minute=45)
        submitted = NOW.replace(hour=9, minute=50)
        out = xp_service.calculate_xp(
            100,
            rating=5,
            started_at=started,
            submitted_at=submitted,
            required_start_time=time(11, 0),  # 未到 -> bonus
            is_challenge=True,
            chain_index=3,
            chain_total=3,
            now=NOW,
        )
        # 1.5 * 1.2 * 1.1 * 1.25 * 1.5 = 3.7125
        # 100 * 3.7125 = 371.25 -> 371
        assert out == 371

    def test_all_factors_negative_path(self):
        """1 星 + 超时 + 超速度窗口 -> 多种负向叠加。"""
        started = NOW.replace(hour=7, minute=0)  # 3h 前
        submitted = NOW
        out = xp_service.calculate_xp(
            100,
            rating=1,
            started_at=started,
            submitted_at=submitted,
            required_start_time=time(8, 0),  # 已过 -> penalty
            now=NOW,
        )
        # 0.6 * 0.8 = 0.48 -> 48
        assert out == 48

    def test_cfg_override(self):
        cfg = default_cfg(challenge_bonus=2.0)
        out = xp_service.calculate_xp(100, rating=3, is_challenge=True, cfg=cfg, now=NOW)
        assert out == 200


# ---- 升级判定 -----------------------------------------------------------

class TestApplyXpAndLevel:
    def test_zero_xp_no_levelup(self):
        child = make_child(level=3, xp=0)
        info = xp_service.apply_xp_and_level(child, 0)
        assert info["leveled_up"] is False
        assert info["levels_gained"] == 0
        assert child.level == 3
        assert child.xp == 0

    def test_partial_xp_no_levelup(self):
        child = make_child(level=3, xp=0)
        needed = xp_service.xp_required_for_level(3)  # 450
        info = xp_service.apply_xp_and_level(child, needed - 50)
        assert info["leveled_up"] is False
        assert child.level == 3
        assert child.xp == needed - 50
        assert info["next_level_xp_required"] == needed

    def test_exact_levelup(self):
        child = make_child(level=3, xp=0)
        needed = xp_service.xp_required_for_level(3)  # 450
        info = xp_service.apply_xp_and_level(child, needed)
        assert info["leveled_up"] is True
        assert info["levels_gained"] == 1
        assert child.level == 4
        assert child.xp == 0
        assert info["next_level_xp_required"] == xp_service.xp_required_for_level(4)

    def test_cross_multiple_levels(self):
        """一次大额经验应能跨多级。"""
        child = make_child(level=1, xp=0)
        # 累计到 6 级所需: sum(L=1..5)
        total_to_6 = sum(xp_service.xp_required_for_level(L) for L in range(1, 6))
        info = xp_service.apply_xp_and_level(child, total_to_6)
        assert info["levels_gained"] == 5
        assert child.level == 6
        assert child.xp == 0
        assert info["next_level_xp_required"] == xp_service.xp_required_for_level(6)

    def test_xp_remainder_after_levelup(self):
        child = make_child(level=1, xp=0)
        needed = xp_service.xp_required_for_level(1)  # 200
        xp_service.apply_xp_and_level(child, needed + 50)
        assert child.level == 2
        assert child.xp == 50

    def test_existing_xp_carryover(self):
        child = make_child(level=3, xp=200)
        needed = xp_service.xp_required_for_level(3)  # 450
        # 已有 200,再给 enough to level up
        give = needed - 200 + 25
        info = xp_service.apply_xp_and_level(child, give)
        assert child.level == 4
        assert child.xp == 25
        assert info["levels_gained"] == 1

    def test_cfg_override_levels(self):
        """配置改 base/growth 后,升级阈值随之变化。"""
        child = make_child(level=1, xp=0)
        cfg = default_cfg(base_xp=100, growth=2.0)
        # 1->2 需 100
        info = xp_service.apply_xp_and_level(child, 100, cfg=cfg)
        assert child.level == 2
        assert child.xp == 0
        # 2->3 需 200
        assert info["next_level_xp_required"] == 200


# ---- 边界:浮点 round 行为 ----------------------------------------------

class TestRounding:
    def test_rounding_nearest(self):
        """XP 计算最终用 round()."""
        # base=33, rating=3, is_challenge -> 33*1.0*1.25 = 41.25 -> 41 (banker's rounding 走 nearest-even -> 41)
        out = xp_service.calculate_xp(33, rating=3, is_challenge=True, now=NOW)
        assert out == 41

    def test_curve_is_internally_consistent(self):
        """任意 level 的曲线都应等于 base*growth^(L-1) 的 round。"""
        base, growth = 200, 1.5
        for L in range(1, 25):
            expected = int(round(base * (growth ** (L - 1))))
            assert xp_service.xp_required_for_level(L, base_xp=base, growth=growth) == expected
