"""TaskRead.rejected 派生真值表单测(DEV-56 路线 2)。

驳回后实例仍停在 `IN_PROGRESS`(零状态机改动),展示态由后端在 `_to_read`
单点派生:

    rejected = (status == IN_PROGRESS and review_comment is not None
                and submitted_at is None)

不依赖 DB,只针对纯函数;`ScnTaskInstance` 用 `SimpleNamespace` 代替。
派生为何成立(IN_PROGRESS + 评语 ⟹ 曾被驳回)见
`app/api/v1/tasks.py:_to_read` 的不变式注释。
"""
from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.api.v1.tasks import _to_read
from app.models.enums import ContentSource, TaskStatus
from app.schemas.task import TaskRead

_TS = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def make_task(**overrides) -> SimpleNamespace:
    """最小可喂给 `_to_read` 的实例桩;默认 = 普通进行中任务(非驳回)。"""
    base = {
        "id": "task-1",
        "family_id": "family-1",
        "season_id": "season-1",
        "template_id": "template-1",
        "creator_account_id": "account-parent",
        "target_child_id": "child-1",
        "assignee_child_id": "child-1",
        "title": "打扫房间",
        "description": "",
        "lore_snippet": None,
        "xp_reward": 50,
        "status": TaskStatus.IN_PROGRESS,
        "deadline": None,
        "expire_at": None,
        "generated_for_date": None,
        "difficulty": None,
        "proof_object_key": None,
        "rating": None,
        "review_comment": None,
        "xp_awarded": None,
        "coin_delta": 0,
        "abandon_count_at_submit": 0,
        "started_at": _TS,
        "submitted_at": None,
        "completed_at": None,
        "time_deposit": 10,
        "chain_index": None,
        "chain_total": None,
        "content_source": ContentSource.TEMPLATE,
        "template": None,
        "participants": [],
        "created_at": _TS,
        "updated_at": _TS,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def rejected_of(**overrides) -> bool:
    return _to_read(make_task(**overrides)).rejected


# ---- 真值表 -------------------------------------------------------------

@pytest.mark.parametrize(
    "case",
    [
        pytest.param(
            {"status": TaskStatus.PENDING_REVIEW, "review_comment": "再改改", "submitted_at": _TS},
            id="pending_review-with-comment",
        ),
        pytest.param(
            {"status": TaskStatus.COMPLETED, "review_comment": "做得好", "submitted_at": _TS},
            id="completed-with-comment",
        ),
        pytest.param(
            {"status": TaskStatus.IN_PROGRESS, "review_comment": None, "submitted_at": None},
            id="in_progress-no-comment",
        ),
        pytest.param(
            {"status": TaskStatus.AVAILABLE, "review_comment": None, "submitted_at": None},
            id="available-untouched",
        ),
        pytest.param(
            {"status": TaskStatus.EXPIRED, "review_comment": "再改改", "submitted_at": None},
            id="expired-with-comment",
        ),
        pytest.param(
            # 重交后:`submit_task` 会重写 submitted_at,驳回态回落。
            {"status": TaskStatus.IN_PROGRESS, "review_comment": "再改改", "submitted_at": _TS},
            id="in_progress-resubmitted",
        ),
        pytest.param(
            # 普通进行中:有提交时间、无评语(未被审核过)。
            {"status": TaskStatus.IN_PROGRESS, "review_comment": None, "submitted_at": _TS},
            id="in_progress-plain",
        ),
    ],
)
def test_rejected_false(case: dict) -> None:
    assert rejected_of(**case) is False


@pytest.mark.parametrize(
    "case",
    [
        pytest.param(
            {
                "status": TaskStatus.IN_PROGRESS,
                "review_comment": "照片不清晰,请重拍",
                "submitted_at": None,
            },
            id="in_progress-rejected",
        ),
        pytest.param(
            # 家长留空评语驳回:仍须可见驳回态(故判空用 is not None 而非非空串)。
            {"status": TaskStatus.IN_PROGRESS, "review_comment": "", "submitted_at": None},
            id="in_progress-rejected-empty-comment",
        ),
    ],
)
def test_rejected_true(case: dict) -> None:
    assert rejected_of(**case) is True


def test_default_field_value_is_false() -> None:
    """契约:`TaskRead.rejected` 默认 False,旧客户端/未派生路径不受影响。"""
    assert TaskRead.model_fields["rejected"].default is False


def test_field_exposed_on_read_model() -> None:
    """派生值确实落到 TaskRead 上(而非仅局部变量)。"""
    read = _to_read(
        make_task(status=TaskStatus.IN_PROGRESS, review_comment="再改改", submitted_at=None)
    )
    assert read.rejected is True
    # 驳回原因由既有 review_comment 承载,不新增字段。
    assert read.review_comment == "再改改"