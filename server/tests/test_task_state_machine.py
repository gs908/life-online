"""任务状态机闭环测试(DEV-8)。

状态机:AVAILABLE -> IN_PROGRESS -> PENDING_REVIEW -> COMPLETED
                                        |  ^
                                        v  |(驳回,不动押金)
                                     IN_PROGRESS
       AVAILABLE / IN_PROGRESS --(expire_at 已过)--> EXPIRED

覆盖:
- 创建 -> 接取 -> 提交 -> 审核通过 -> 完成 全链路,含 XP 发放与押金退还。
- 审核驳回:PENDING_REVIEW -> IN_PROGRESS,押金不变,可重新提交。
- 放弃任务:押金退款 + 连续放弃(当日第 4 次起)60% 惩罚。
- 过期任务:AVAILABLE 直接过期;IN_PROGRESS 过期全额退押金,不计入放弃惩罚。
- 非法状态流转:对每个动作在错误状态下调用,断言 409。
- 家长/孩子权限边界:孩子不能创建/删除/审核/驳回任务;家长不能接取/提交/放弃任务;
  跨家庭访问一律 403/404,不泄露资源是否存在于别的家庭。

需要可连接的数据库(远程优先),不可达时该模块内用例会被 `db_ready` fixture 跳过。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import AsyncIterator

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.dev.seed import SeededFamily, cleanup_family, seed_basic_family
from app.models.enums import TaskStatus
from app.services import auth_service, task_service

pytestmark = pytest.mark.db


def _auth_headers(account) -> dict[str, str]:
    tokens = auth_service.issue_token_pair(account)
    return {"Authorization": f"Bearer {tokens.access_token}"}


async def _create_task(
    api_client: AsyncClient, parent_headers: dict[str, str], seeded_family: SeededFamily, **overrides
) -> dict:
    body = {
        "season_id": seeded_family.season.id,
        "title": "打扫房间",
        "xp_reward": 50,
        "time_deposit": 10,
        "target_child_id": seeded_family.child.id,
        **overrides,
    }
    resp = await api_client.post("/api/v1/scn/task-instances", json=body, headers=parent_headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


@pytest_asyncio.fixture
async def other_family(db_session: AsyncSession) -> AsyncIterator[SeededFamily]:
    """第二个家庭,专门用于跨家庭隔离断言。"""
    seeded = await seed_basic_family(db_session, suffix="task-other")
    try:
        yield seeded
    finally:
        await cleanup_family(db_session, seeded.family.id)


async def _top_up(db_session: AsyncSession, seeded_family: SeededFamily, amount: int = 100) -> None:
    seeded_family.child.time_coin_balance = amount
    await db_session.commit()


async def test_full_lifecycle_create_start_submit_approve(
    api_client: AsyncClient, seeded_family: SeededFamily, db_session: AsyncSession
) -> None:
    await _top_up(db_session, seeded_family)
    parent_headers = _auth_headers(seeded_family.parent)
    child_headers = _auth_headers(seeded_family.child_account)

    task = await _create_task(api_client, parent_headers, seeded_family)
    assert task["status"] == TaskStatus.AVAILABLE.value

    start_resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/start", headers=child_headers
    )
    assert start_resp.status_code == 200
    started = start_resp.json()["data"]
    assert started["status"] == TaskStatus.IN_PROGRESS.value
    assert started["assignee_child_id"] == seeded_family.child.id

    submit_resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/submit",
        json={"proof_object_key": "proofs/1.jpg"},
        headers=child_headers,
    )
    assert submit_resp.status_code == 200
    submitted = submit_resp.json()["data"]
    assert submitted["status"] == TaskStatus.PENDING_REVIEW.value

    approve_resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/approve",
        json={"rating": 5, "comment": "做得好"},
        headers=parent_headers,
    )
    assert approve_resp.status_code == 200
    completed = approve_resp.json()["data"]
    assert completed["status"] == TaskStatus.COMPLETED.value
    assert completed["rating"] == 5
    assert completed["xp_awarded"] is not None and completed["xp_awarded"] > 0
    assert completed["coin_delta"] == 10  # 押金全额退还

    await db_session.refresh(seeded_family.child)
    assert seeded_family.child.time_coin_balance == 100  # 押金扣了又退,净额不变


async def test_reject_sends_back_to_in_progress_without_touching_deposit(
    api_client: AsyncClient, seeded_family: SeededFamily, db_session: AsyncSession
) -> None:
    await _top_up(db_session, seeded_family)
    parent_headers = _auth_headers(seeded_family.parent)
    child_headers = _auth_headers(seeded_family.child_account)

    task = await _create_task(api_client, parent_headers, seeded_family)
    await api_client.post(f"/api/v1/scn/task-instances/{task['id']}/start", headers=child_headers)
    await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/submit",
        json={"proof_object_key": "proofs/1.jpg"},
        headers=child_headers,
    )

    await db_session.refresh(seeded_family.child)
    balance_after_start = seeded_family.child.time_coin_balance

    reject_resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/reject",
        json={"comment": "照片看不清,重新拍一张"},
        headers=parent_headers,
    )
    assert reject_resp.status_code == 200
    rejected = reject_resp.json()["data"]
    assert rejected["status"] == TaskStatus.IN_PROGRESS.value
    assert rejected["review_comment"] == "照片看不清,重新拍一张"

    await db_session.refresh(seeded_family.child)
    assert seeded_family.child.time_coin_balance == balance_after_start  # 驳回不动押金

    # 孩子可以重新提交,家长再次通过
    resubmit_resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/submit",
        json={"proof_object_key": "proofs/2.jpg"},
        headers=child_headers,
    )
    assert resubmit_resp.status_code == 200
    assert resubmit_resp.json()["data"]["status"] == TaskStatus.PENDING_REVIEW.value

    approve_resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/approve",
        json={"rating": 4},
        headers=parent_headers,
    )
    assert approve_resp.status_code == 200
    assert approve_resp.json()["data"]["status"] == TaskStatus.COMPLETED.value


async def test_abandon_refunds_and_penalizes_after_repeated_abandons(
    api_client: AsyncClient, seeded_family: SeededFamily, db_session: AsyncSession
) -> None:
    await _top_up(db_session, seeded_family, amount=1000)
    parent_headers = _auth_headers(seeded_family.parent)
    child_headers = _auth_headers(seeded_family.child_account)

    # 前 3 次放弃:全额退款,接取 + 放弃一个来回后净余额不变
    for _ in range(3):
        await db_session.refresh(seeded_family.child)
        balance_before_start = seeded_family.child.time_coin_balance

        task = await _create_task(api_client, parent_headers, seeded_family)
        await api_client.post(f"/api/v1/scn/task-instances/{task['id']}/start", headers=child_headers)
        abandon_resp = await api_client.post(
            f"/api/v1/scn/task-instances/{task['id']}/abandon", headers=child_headers
        )
        assert abandon_resp.status_code == 200
        abandoned = abandon_resp.json()["data"]
        assert abandoned["status"] == TaskStatus.AVAILABLE.value
        assert abandoned["assignee_child_id"] is None
        await db_session.refresh(seeded_family.child)
        assert seeded_family.child.time_coin_balance == balance_before_start  # 全额退款,净额不变

    await db_session.refresh(seeded_family.child)
    assert seeded_family.child.daily_abandon_count == 3

    # 第 4 次放弃(当日第 4 次,abandon_count_today>=3 触发惩罚):押金 10,只退 60%(6),倒扣 4
    balance_before_start = seeded_family.child.time_coin_balance
    task = await _create_task(api_client, parent_headers, seeded_family)
    await api_client.post(f"/api/v1/scn/task-instances/{task['id']}/start", headers=child_headers)
    abandon_resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/abandon", headers=child_headers
    )
    assert abandon_resp.status_code == 200
    await db_session.refresh(seeded_family.child)
    assert seeded_family.child.time_coin_balance == balance_before_start - 4  # 净亏 10 - 6
    assert seeded_family.child.daily_abandon_count == 4


async def test_expire_overdue_tasks(
    api_client: AsyncClient, seeded_family: SeededFamily, db_session: AsyncSession
) -> None:
    await _top_up(db_session, seeded_family)
    parent_headers = _auth_headers(seeded_family.parent)
    child_headers = _auth_headers(seeded_family.child_account)
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).replace(tzinfo=None).isoformat()

    available_task = await _create_task(api_client, parent_headers, seeded_family, expire_at=past)

    in_progress_task = await _create_task(api_client, parent_headers, seeded_family, expire_at=past)
    await api_client.post(
        f"/api/v1/scn/task-instances/{in_progress_task['id']}/start", headers=child_headers
    )
    await db_session.refresh(seeded_family.child)
    balance_after_start = seeded_family.child.time_coin_balance

    processed = await task_service.expire_overdue_tasks(db_session)
    assert processed == 2

    available_after = await task_service.get_task(db_session, available_task["id"])
    assert available_after.status == TaskStatus.EXPIRED

    in_progress_after = await task_service.get_task(db_session, in_progress_task["id"])
    assert in_progress_after.status == TaskStatus.EXPIRED

    await db_session.refresh(seeded_family.child)
    assert seeded_family.child.time_coin_balance == balance_after_start + 10  # 全额退押金
    assert seeded_family.child.daily_abandon_count == 0  # 不计入放弃惩罚


async def test_illegal_transitions_return_conflict(
    api_client: AsyncClient, seeded_family: SeededFamily, db_session: AsyncSession
) -> None:
    await _top_up(db_session, seeded_family)
    parent_headers = _auth_headers(seeded_family.parent)
    child_headers = _auth_headers(seeded_family.child_account)

    task = await _create_task(api_client, parent_headers, seeded_family)

    # AVAILABLE 状态下 approve/reject 先过 status 校验,直接 409;
    # submit/abandon 服务层先校验"你是不是接取人"(assignee_child_id 尚为空),
    # 未接取时先命中 403,而不是 409 —— 这也是权限边界优先于状态机的既定顺序。
    for path, headers, body in [
        ("approve", parent_headers, {"rating": 5}),
        ("reject", parent_headers, {}),
    ]:
        resp = await api_client.post(
            f"/api/v1/scn/task-instances/{task['id']}/{path}",
            json=body,
            headers=headers,
        )
        assert resp.status_code == 409, f"{path} 在 AVAILABLE 状态下应返回 409,实际 {resp.status_code}"

    for path, headers, body in [
        ("submit", child_headers, {"proof_object_key": "x"}),
        ("abandon", child_headers, None),
    ]:
        resp = await api_client.post(
            f"/api/v1/scn/task-instances/{task['id']}/{path}",
            json=body,
            headers=headers,
        )
        assert resp.status_code == 403, f"{path} 在未接取时应返回 403,实际 {resp.status_code}"

    await api_client.post(f"/api/v1/scn/task-instances/{task['id']}/start", headers=child_headers)

    # IN_PROGRESS 状态下不能重复接取/审核/驳回
    start_again = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/start", headers=child_headers
    )
    assert start_again.status_code == 409

    approve_too_early = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/approve", json={"rating": 5}, headers=parent_headers
    )
    assert approve_too_early.status_code == 409

    reject_too_early = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/reject", json={}, headers=parent_headers
    )
    assert reject_too_early.status_code == 409

    await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/submit",
        json={"proof_object_key": "proofs/1.jpg"},
        headers=child_headers,
    )

    # PENDING_REVIEW 状态下孩子不能再次提交/放弃
    submit_again = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/submit",
        json={"proof_object_key": "proofs/2.jpg"},
        headers=child_headers,
    )
    assert submit_again.status_code == 409

    abandon_after_submit = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/abandon", headers=child_headers
    )
    assert abandon_after_submit.status_code == 409

    approve_resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/approve", json={"rating": 5}, headers=parent_headers
    )
    assert approve_resp.status_code == 200

    # COMPLETED 状态下任何流转都非法
    for path, headers, body in [
        ("start", child_headers, None),
        ("submit", child_headers, {"proof_object_key": "x"}),
        ("approve", parent_headers, {"rating": 5}),
        ("reject", parent_headers, {}),
        ("abandon", child_headers, None),
    ]:
        resp = await api_client.post(
            f"/api/v1/scn/task-instances/{task['id']}/{path}",
            json=body,
            headers=headers,
        )
        assert resp.status_code == 409, f"{path} 在 COMPLETED 状态下应返回 409,实际 {resp.status_code}"


async def test_permission_boundaries(
    api_client: AsyncClient, seeded_family: SeededFamily, db_session: AsyncSession
) -> None:
    await _top_up(db_session, seeded_family)
    parent_headers = _auth_headers(seeded_family.parent)
    child_headers = _auth_headers(seeded_family.child_account)

    # 孩子不能创建/删除任务
    create_by_child = await api_client.post(
        "/api/v1/scn/task-instances",
        json={"season_id": seeded_family.season.id, "title": "越权创建"},
        headers=child_headers,
    )
    assert create_by_child.status_code == 403

    task = await _create_task(api_client, parent_headers, seeded_family)

    delete_by_child = await api_client.delete(
        f"/api/v1/scn/task-instances/{task['id']}", headers=child_headers
    )
    assert delete_by_child.status_code == 403

    # 家长不能接取/提交/放弃任务(只有 ADVENTURER 可操作)
    start_by_parent = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/start", headers=parent_headers
    )
    assert start_by_parent.status_code == 403

    await api_client.post(f"/api/v1/scn/task-instances/{task['id']}/start", headers=child_headers)

    submit_by_parent = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/submit",
        json={"proof_object_key": "x"},
        headers=parent_headers,
    )
    assert submit_by_parent.status_code == 403

    abandon_by_parent = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/abandon", headers=parent_headers
    )
    assert abandon_by_parent.status_code == 403

    # 孩子不能审核/驳回任务
    await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/submit",
        json={"proof_object_key": "x"},
        headers=child_headers,
    )
    approve_by_child = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/approve", json={"rating": 5}, headers=child_headers
    )
    assert approve_by_child.status_code == 403
    reject_by_child = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/reject", json={}, headers=child_headers
    )
    assert reject_by_child.status_code == 403


async def test_cross_family_isolation(
    api_client: AsyncClient, seeded_family: SeededFamily, other_family: SeededFamily, db_session: AsyncSession
) -> None:
    await _top_up(db_session, seeded_family)
    parent_headers = _auth_headers(seeded_family.parent)
    other_parent_headers = _auth_headers(other_family.parent)
    other_child_headers = _auth_headers(other_family.child_account)

    task = await _create_task(api_client, parent_headers, seeded_family)

    # 另一个家庭的家长不能查看/审核/驳回/删除这个任务
    get_resp = await api_client.get(
        f"/api/v1/scn/task-instances/{task['id']}", headers=other_parent_headers
    )
    assert get_resp.status_code == 403

    approve_resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/approve",
        json={"rating": 5},
        headers=other_parent_headers,
    )
    assert approve_resp.status_code == 403

    delete_resp = await api_client.delete(
        f"/api/v1/scn/task-instances/{task['id']}", headers=other_parent_headers
    )
    assert delete_resp.status_code == 403

    # 另一个家庭的孩子不能接取这个任务
    start_resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/start", headers=other_child_headers
    )
    assert start_resp.status_code == 403

    # 列表接口只返回自己家庭的任务
    list_resp = await api_client.get("/api/v1/scn/task-instances", headers=other_parent_headers)
    assert list_resp.status_code == 200
    listed_ids = {t["id"] for t in list_resp.json()["data"]["items"]}
    assert task["id"] not in listed_ids
