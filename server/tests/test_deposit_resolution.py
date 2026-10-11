"""押金解析测试(DEV-34 块 C:押金 = 耗时驱动)。

覆盖验收要点:
- 各类型缺省押金(by_type 默认值);
- 耗时 0.5x / 1x / 2x(estimated_minutes / reference_minutes)三档;
- 显式值优先,显式越界 clamp 到类型 min/max,负数报错;
- 配额上限封顶(floor(当日配额 x allowance_cap_ratio));
- 难度只改 XP 不改押金(difficulty 不参与押金公式,XP 按倍率表缩放);
- 超时退款 / 放弃退款比例走 DepositSection 配置。

主体为纯函数单测(不依赖 DB);末尾一条 DB 用例走 preview-deposit 接口。
"""
from __future__ import annotations

import pytest

from app.common.exceptions import ValidationError
from app.config import DepositSection, DepositTypeRange, XpSection
from app.models.enums import TaskType
from app.services import coin_service, xp_service

ALLOWANCE = 100  # 默认家庭日配额,cap = floor(100 * 0.5) = 50


def default_cfg(**overrides) -> DepositSection:
    cfg = DepositSection()
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


def deposit(task_type: TaskType | str, *, estimated=None, explicit=None, allowance=ALLOWANCE, cfg=None) -> int:
    return coin_service.compute_deposit(
        task_type=task_type,
        estimated_minutes=estimated,
        explicit_deposit=explicit,
        daily_allowance=allowance,
        cfg=cfg,
    )


# ---- 各类型缺省 ----------------------------------------------------------

class TestTypeDefaults:
    @pytest.mark.parametrize(
        ("task_type", "expected"),
        [
            (TaskType.DAILY, 10),
            (TaskType.CHALLENGE, 30),
            (TaskType.CHAIN, 20),
            (TaskType.TIMED, 25),
            (TaskType.COOP, 5),
            ("HIDDEN", 0),  # 隐藏任务(系统投放)不占押金;枚举外键按字符串查表
        ],
    )
    def test_default_per_type(self, task_type, expected):
        assert deposit(task_type) == expected

    def test_unknown_type_rejected(self):
        with pytest.raises(ValidationError):
            deposit("NO_SUCH_TYPE")


# ---- 耗时驱动 ------------------------------------------------------------

class TestTimeDriven:
    """ratio = clamp(estimated / reference_minutes, 0.5, 2.0),value = round(default x ratio)。"""

    def test_half_ratio_hits_daily_min(self):
        # 15/30 = 0.5x -> 10 * 0.5 = 5(DAILY 下限)
        assert deposit(TaskType.DAILY, estimated=15) == 5

    def test_one_ratio_is_default(self):
        # 30/30 = 1x -> 默认值本身
        assert deposit(TaskType.DAILY, estimated=30) == 10

    def test_two_ratio_hits_daily_max(self):
        # 60/30 = 2x -> 20(DAILY 上限)
        assert deposit(TaskType.DAILY, estimated=60) == 20

    def test_ratio_clamped_at_2x(self):
        # 90 分钟 -> ratio 仍为 2.0 -> 20,不会超上限
        assert deposit(TaskType.DAILY, estimated=90) == 20

    def test_ratio_clamped_at_0_5x(self):
        # 5 分钟 -> ratio 仍为 0.5 -> 5,不会低于下限
        assert deposit(TaskType.DAILY, estimated=5) == 5

    def test_challenge_half_ratio(self):
        # 15/30 = 0.5x -> 30 * 0.5 = 15(CHALLENGE 下限)
        assert deposit(TaskType.CHALLENGE, estimated=15) == 15

    def test_odd_default_half_ratio_rounds_half_up(self):
        """奇数默认值 x 0.5 出现 .5 时四舍五入(HALF_UP),不用银行家舍入。

        COOP 5 x 0.5 = 2.5 -> 3(banker's round 会得 2;COOP min=0,min/max clamp
        不掩盖取整结果)。TIMED 25 x 0.5 = 12.5 -> 13(banker's round 会得 12),
        但默认 min=15 会把 13 再 clamp 回 15,故这里把 min 放宽到 10 观察公式本身。
        """
        assert deposit(TaskType.COOP, estimated=15) == 3
        cfg = default_cfg()
        cfg.by_type["TIMED"] = DepositTypeRange(default=25, min=10, max=40)
        assert deposit(TaskType.TIMED, estimated=15, cfg=cfg) == 13

    def test_missing_estimated_falls_back_to_default(self):
        # 未填耗时 -> 类型默认值(不再有写死的 `or 10` 兜底)
        assert deposit(TaskType.TIMED) == 25

    def test_custom_reference_minutes(self):
        cfg = default_cfg(reference_minutes=60)
        assert deposit(TaskType.DAILY, estimated=30, cfg=cfg) == 5  # 30/60=0.5x
        assert deposit(TaskType.DAILY, estimated=120, cfg=cfg) == 20  # 2x


# ---- 显式值 --------------------------------------------------------------

class TestExplicitDeposit:
    def test_explicit_overrides_time_formula(self):
        # 显式 18 优先于耗时公式(60 分钟本应算 20)
        assert deposit(TaskType.DAILY, estimated=60, explicit=18) == 18

    def test_explicit_above_max_clamped(self):
        assert deposit(TaskType.DAILY, explicit=99) == 20

    def test_explicit_below_min_clamped(self):
        assert deposit(TaskType.DAILY, explicit=1) == 5

    def test_explicit_zero_rejected(self):
        with pytest.raises(ValidationError):
            deposit(TaskType.DAILY, explicit=-1)

    def test_explicit_zero_ok_for_coop(self):
        # COOP min=0,显式 0 合法(协作任务免押金)
        assert deposit(TaskType.COOP, explicit=0) == 0


# ---- 配额封顶 ------------------------------------------------------------

class TestAllowanceCap:
    def test_capped_by_half_allowance(self):
        # CHALLENGE 默认 30,配额 40 -> cap = 20 -> 封顶
        assert deposit(TaskType.CHALLENGE, allowance=40) == 20

    def test_cap_uses_floor(self):
        # 配额 45 -> cap = floor(22.5) = 22,CHALLENGE 默认 30 -> 22
        assert deposit(TaskType.CHALLENGE, allowance=45) == 22

    def test_below_cap_untouched(self):
        # DAILY 20 < cap 50,不受影响
        assert deposit(TaskType.DAILY, estimated=60) == 20

    def test_cap_ratio_configurable(self):
        cfg = default_cfg(allowance_cap_ratio=0.2)
        # 配额 100, ratio 0.2 -> cap 20,DAILY 上限恰为 20
        assert deposit(TaskType.DAILY, estimated=60, cfg=cfg) == 20
        # CHALLENGE 默认 30 -> 封顶 20
        assert deposit(TaskType.CHALLENGE, cfg=cfg) == 20

    def test_deposit_cap_helper(self):
        assert coin_service.deposit_cap(100) == 50
        assert coin_service.deposit_cap(45) == 22


# ---- 封顶标志(仅真正截断时置位) ------------------------------------------

class TestCappedFlag:
    def detail(self, **kwargs) -> tuple[int, bool]:
        return coin_service.compute_deposit_detail(**kwargs)

    def test_truncated_by_cap_sets_flag(self):
        # CHALLENGE 默认 30,配额 40 -> cap 20,30 > 20 真截断
        assert self.detail(task_type=TaskType.CHALLENGE, daily_allowance=40) == (20, True)

    def test_equal_to_cap_without_truncation_clears_flag(self):
        # CHALLENGE 显式 50 恰好等于 cap 50,非截断 -> False(封顶态是前端视觉提示依据)
        assert self.detail(
            task_type=TaskType.CHALLENGE, explicit_deposit=50, daily_allowance=100
        ) == (50, False)

    def test_hidden_zero_allowance_zero_not_capped(self):
        # HIDDEN 0 / 配额 0:0 不大于 cap 0,非截断
        assert self.detail(task_type="HIDDEN", daily_allowance=0) == (0, False)

    def test_below_cap_clears_flag(self):
        assert self.detail(
            task_type=TaskType.DAILY, estimated_minutes=30, daily_allowance=100
        ) == (10, False)


# ---- 难度只改 XP 不改押金 --------------------------------------------------

class TestDifficultyAffectsXpOnly:
    def test_deposit_ignores_difficulty(self):
        # 押金公式根本没有 difficulty 入参:同一类型+耗时,押金唯一
        base = deposit(TaskType.DAILY, estimated=30)
        assert base == 10
        for _difficulty in range(1, 6):
            assert deposit(TaskType.DAILY, estimated=30) == 10

    def test_xp_scales_with_difficulty(self):
        # 同样 rating=3,XP 随难度 1->5 单调放大:0.9 / 1.0 / 1.1 / 1.25 / 1.4
        xps = [xp_service.calculate_xp(100, rating=3, difficulty=d) for d in range(1, 6)]
        assert xps == [90, 100, 110, 125, 140]
        assert xps == sorted(xps)

    def test_difficulty_none_keeps_legacy_xp(self):
        # 存量模板无难度 -> 倍率 1.0,XP 行为不变
        assert xp_service.calculate_xp(100, rating=3, difficulty=None) == 100

    def test_difficulty_out_of_range_clamped(self):
        assert xp_service.calculate_xp(100, rating=3, difficulty=0) == 90  # clamp 到 1
        assert xp_service.calculate_xp(100, rating=3, difficulty=9) == 140  # clamp 到 5

    def test_difficulty_multiplies_with_rating(self):
        # 与星级相乘:rating 5(1.5) x difficulty 4(1.25) = 1.875
        assert xp_service.calculate_xp(100, rating=5, difficulty=4) == 188

    def test_difficulty_multiplier_from_config(self):
        cfg = XpSection()
        cfg.difficulty_multiplier = {1: 1.0, 2: 1.0, 3: 2.0, 4: 1.0, 5: 1.0}
        assert xp_service.calculate_xp(100, rating=3, difficulty=3, cfg=cfg) == 200


# ---- 退款/扣罚比例(块 D 配置) -------------------------------------------

class TestRefundRatios:
    def test_timeout_refund_half(self):
        assert coin_service.calculate_timeout_refund(10) == 5
        assert coin_service.calculate_timeout_refund(20) == 10
        assert coin_service.calculate_timeout_refund(15) == 7  # int() 向下取整,罚 8
        assert coin_service.calculate_timeout_refund(0) == 0

    def test_timeout_refund_ratio_configurable(self, monkeypatch):
        monkeypatch.setattr(coin_service.settings.deposit, "timeout_refund_ratio", 0.8)
        assert coin_service.calculate_timeout_refund(10) == 8

    def test_abandon_refund_config_driven(self):
        # 前 3 次全额,之后 60%
        assert coin_service.calculate_refund(10, 2) == 10
        assert coin_service.calculate_refund(10, 3) == 6


# ---- preview-deposit 接口(DB) -------------------------------------------

@pytest.mark.db
async def test_preview_deposit_endpoint(api_client, seeded_family) -> None:
    """POST /scn/task-templates/preview-deposit:难度不影响押金,显式越界被 clamp。"""
    from app.services import auth_service

    def _auth_headers(account) -> dict[str, str]:
        tokens = auth_service.issue_token_pair(account)
        return {"Authorization": f"Bearer {tokens.access_token}"}

    headers = _auth_headers(seeded_family.parent)

    resp = await api_client.post(
        "/api/v1/scn/task-templates/preview-deposit",
        json={"type": "DAILY", "estimated_minutes": 60, "difficulty": 5},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    # 难度 5 不放大押金:60 分钟 DAILY 仍是 20(类型上限);默认家庭配额 100(cap 50),不封顶
    assert data["time_deposit"] == 20
    assert data["capped_by_allowance"] is False

    # 显式越界 clamp:CHALLENGE 显式 99 -> 50(类型上限)
    resp2 = await api_client.post(
        "/api/v1/scn/task-templates/preview-deposit",
        json={"type": "CHALLENGE", "time_deposit": 99},
        headers=headers,
    )
    assert resp2.status_code == 200, resp2.text
    data2 = resp2.json()["data"]
    assert data2["time_deposit"] == 50
    # 50 恰好等于 cap 50 但非截断,不得误报封顶(前端视觉提示依据)
    assert data2["capped_by_allowance"] is False

    # 孩子无权调用(仅父母)
    child_headers = _auth_headers(seeded_family.child_account)
    resp3 = await api_client.post(
        "/api/v1/scn/task-templates/preview-deposit",
        json={"type": "DAILY"},
        headers=child_headers,
    )
    assert resp3.status_code == 403
