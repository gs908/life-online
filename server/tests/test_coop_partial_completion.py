"""COOP「部分完成」状态机(DEV-40,docs/13 定稿版)。

覆盖 docs/13 定稿版 §8 清单:
- 参与者子状态迁移全路径(JOINED → SUBMITTED → DONE / QUIT);
- 逐人 approve 守卫(IN_PROGRESS/PENDING_REVIEW + 该参与者 SUBMITTED);
- 部分通过判退(显式 settle_partial,漏传 409;阶梯退款不递增放弃计数);
- leave 语义(主动放弃:递增计数;OWNER 不可 leave);
- reject 路径(SUBMITTED → JOINED、proof 保留);
- 全员 DONE / 全员提交聚合 COMPLETED;
- Q4 分母行为修改(最终交付的孩子参与者数;家长不入分母;从未提交者不分 XP);
- Q3 家长交付走 proof(uploaded_by 透出);
- COOP 过期全额退、不复活(块 F 既定口径,docs/13 §5 加注)。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dev.seed import SeededFamily
from app.models.enums import (
    CoinTransactionType,
    NotificationType,
    TaskParticipantRole,
    TaskParticipantStatus,
    TaskStatus,
    TaskType,
    UploadPurpose,
)
from app.models.scn_notification import ScnNotification
from app.models.scn_task_instance import ScnTaskInstance
from app.models.scn_task_participant import ScnTaskParticipant
from app.models.sys_upload import SysUpload
from app.services import coop_service, task_service, xp_service
from tests.conftest import db_ready  # noqa: F401  (fixture 依赖声明)

pytestmark = pytest.mark.usefixtures("db_ready")


# ---------------------------------------------------------------------------
# helpers(与 test_task_state_machine 同口径)
# ---------------------------------------------------------------------------

async def _top_up(db_session: AsyncSession, seeded_family: SeededFamily, amount: int = 100) -> None:
    seeded_family.child.time_coin_balance = amount
    await db_session.commit()


def _auth_headers(account) -> dict[str, str]:
    from app.services import auth_service

    tokens = auth_service.issue_token_pair(account)
    return {"Authorization": f"Bearer {tokens.access_token}"}


async def _second_child_account(db_session: AsyncSession, seeded_family: SeededFamily):
    """再造一个孩子(多孩子协作用),返回 (account, child)。"""
    from app.models.sys_child import SysChild
    from app.services import family_service

    account = await family_service.create_adventurer(
        db_session, family_id=seeded_family.family.id, name=f"二孩-{uuid4().hex[:4]}"
    )
    child = (
        await db_session.execute(select(SysChild).where(SysChild.account_id == account.id))
    ).scalar_one()
    return account, child


async def _proof_key_for(
    db_session: AsyncSession, seeded_family: SeededFamily, account, label: str = "p"
) -> str:
    """为指定账号造一条真实归属的 task_proof 上传记录(家长代交用同款)。"""
    key = f"proofs/{account.id}/{uuid4().hex}-{label}.jpg"
    db_session.add(SysUpload(
        family_id=seeded_family.family.id,
        uploader_account_id=account.id,
        storage_provider="local",
        object_key=key,
        bucket="local",
        public_url=f"/api/v1/files/{key}",
        content_type="image/jpeg",
        size=1,
        purpose=UploadPurpose.TASK_PROOF,
    ))
    await db_session.commit()
    return key


async def _create_coop_task(
    api_client: AsyncClient, parent_headers: dict[str, str], seeded_family: SeededFamily, **overrides
) -> dict:
    body = {
        "season_id": seeded_family.season.id,
        "title": "一起大扫除",
        "type": TaskType.COOP.value,
        "xp_reward": 50,
        "time_deposit": 20,
        "target_child_id": None,
        **overrides,
    }
    resp = await api_client.post("/api/v1/scn/task-instances", json=body, headers=parent_headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


async def _setup_two_children(db_session: AsyncSession, seeded_family: SeededFamily):
    """A=种子里的大孩, B=二孩,各 100 币;返回 (a_account, b_account, b_child)。"""
    await _top_up(db_session, seeded_family, amount=100)
    b_account, b_child = await _second_child_account(db_session, seeded_family)
    b_child.time_coin_balance = 100
    await db_session.commit()
    return seeded_family.child_account, b_account, b_child


async def _statuses(db_session: AsyncSession, task_id: str) -> dict:
    rows = (
        await db_session.execute(
            select(ScnTaskParticipant).where(ScnTaskParticipant.task_instance_id == task_id)
        )
    ).scalars().all()
    return {r.role: TaskParticipantStatus(r.participant_status or "JOINED") for r in rows}


async def _notifications(db_session: AsyncSession, account_id: str, type_: NotificationType) -> list[ScnNotification]:
    rows = (
        await db_session.execute(
            select(ScnNotification).where(
                ScnNotification.recipient_account_id == account_id,
                ScnNotification.type == type_,
            )
        )
    ).scalars().all()
    return list(rows)


# ---------------------------------------------------------------------------
# 子状态迁移 + 逐人 approve + 聚合
# ---------------------------------------------------------------------------

async def test_substate_transitions_and_aggregated_completion(
    api_client: AsyncClient, seeded_family: SeededFamily, db_session: AsyncSession
) -> None:
    """JOIN→JOINED,submit→SUBMITTED(实例保持 IN_PROGRESS + 通知),逐人 approve→DONE,
    全员提交→PENDING_REVIEW,整单审批→COMPLETED;XP 按交付孩子数均摊。"""
    a_account, b_account, b_child = await _setup_two_children(db_session, seeded_family)
    parent_headers = _auth_headers(seeded_family.parent)
    a_headers = _auth_headers(a_account)
    b_headers = _auth_headers(b_account)

    task = await _create_coop_task(api_client, parent_headers, seeded_family)
    assert (await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/start", headers=a_headers)
    ).status_code == 200
    assert (await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/join", headers=b_headers)
    ).status_code == 200
    assert await _statuses(db_session, task["id"]) == {
        TaskParticipantRole.OWNER: TaskParticipantStatus.JOINED,
        TaskParticipantRole.MEMBER: TaskParticipantStatus.JOINED,
    }

    # A 交卷:实例仍是 IN_PROGRESS(还有 JOINED),B 收到 COOP_PARTIAL_SUBMITTED
    resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/submit",
        json={"proof_object_key": await _proof_key_for(db_session, seeded_family, a_account, "a")},
        headers=a_headers,
    )
    assert resp.status_code == 200, resp.text
    detail = (await api_client.get(
        f"/api/v1/scn/task-instances/{task['id']}", headers=parent_headers)
    ).json()["data"]
    assert detail["status"] == TaskStatus.IN_PROGRESS.value
    assert (await _statuses(db_session, task["id"]))[TaskParticipantRole.OWNER] == TaskParticipantStatus.SUBMITTED
    assert len(await _notifications(db_session, b_account.id, NotificationType.COOP_PARTIAL_SUBMITTED)) == 1

    # 逐人 approve A:押金即时退,A → DONE;B 仍 JOINED,实例未聚合
    await db_session.refresh(seeded_family.child)
    a_before = seeded_family.child.time_coin_balance
    resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/approve",
        json={"rating": 5, "child_id": seeded_family.child.id},
        headers=parent_headers,
    )
    assert resp.status_code == 200, resp.text
    detail = resp.json()["data"]
    assert detail["status"] == TaskStatus.IN_PROGRESS.value
    roles = await _statuses(db_session, task["id"])
    assert roles[TaskParticipantRole.OWNER] == TaskParticipantStatus.DONE
    await db_session.refresh(seeded_family.child)
    assert seeded_family.child.time_coin_balance == a_before + 10  # 退个人份额

    # B 交卷:全员已交 → PENDING_REVIEW
    resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/submit",
        json={"proof_object_key": await _proof_key_for(db_session, seeded_family, b_account, "b")},
        headers=b_headers,
    )
    assert resp.status_code == 200, resp.text
    detail = (await api_client.get(
        f"/api/v1/scn/task-instances/{task['id']}", headers=parent_headers)
    ).json()["data"]
    assert detail["status"] == TaskStatus.PENDING_REVIEW.value

    # 整单审批:结算 B(份额 10),聚合 COMPLETED,XP 按交付孩子数(2)均摊
    a_xp_before = seeded_family.child.xp
    b_xp_before = b_child.xp
    resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/approve",
        json={"rating": 5}, headers=parent_headers,
    )
    assert resp.status_code == 200, resp.text
    detail = resp.json()["data"]
    assert detail["status"] == TaskStatus.COMPLETED.value

    task_row = await task_service.get_task(db_session, task["id"])
    expected_total_xp = xp_service.calculate_xp(
        50, rating=5, started_at=task_row.started_at, submitted_at=task_row.submitted_at,
    )
    shares = coop_service.split_evenly(expected_total_xp, 2)
    await db_session.refresh(seeded_family.child)
    await db_session.refresh(b_child)
    assert seeded_family.child.xp == a_xp_before + shares[0]
    assert b_child.xp == b_xp_before + shares[1]
    await db_session.refresh(b_child)
    assert b_child.time_coin_balance == 100  # 整单审批退 B 的份额


async def test_per_person_approve_guards(
    api_client: AsyncClient, seeded_family: SeededFamily, db_session: AsyncSession
) -> None:
    """逐人 approve 守卫:未提交 409;重复确认 409;单人任务带 child_id 422。"""
    a_account, _b_account, _b_child = await _setup_two_children(db_session, seeded_family)
    parent_headers = _auth_headers(seeded_family.parent)
    a_headers = _auth_headers(a_account)

    # 单人任务不支持逐人确认
    body = {"season_id": seeded_family.season.id, "title": "单人", "xp_reward": 10, "time_deposit": 5}
    resp = await api_client.post("/api/v1/scn/task-instances", json=body, headers=parent_headers)
    assert resp.status_code == 200
    single = resp.json()["data"]
    await api_client.post(f"/api/v1/scn/task-instances/{single['id']}/start", headers=a_headers)
    resp = await api_client.post(
        f"/api/v1/scn/task-instances/{single['id']}/approve",
        json={"rating": 5, "child_id": seeded_family.child.id}, headers=parent_headers,
    )
    assert resp.status_code == 422, resp.text

    task = await _create_coop_task(api_client, parent_headers, seeded_family)
    await api_client.post(f"/api/v1/scn/task-instances/{task['id']}/start", headers=a_headers)

    # A 未提交:逐人确认 409
    resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/approve",
        json={"rating": 5, "child_id": seeded_family.child.id}, headers=parent_headers,
    )
    assert resp.status_code == 409, resp.text

    await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/submit",
        json={"proof_object_key": await _proof_key_for(db_session, seeded_family, a_account)},
        headers=a_headers,
    )
    resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/approve",
        json={"rating": 5, "child_id": seeded_family.child.id}, headers=parent_headers,
    )
    assert resp.status_code == 200
    # 已 DONE 再确认:409
    resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/approve",
        json={"rating": 5, "child_id": seeded_family.child.id}, headers=parent_headers,
    )
    assert resp.status_code == 409, resp.text


async def test_whole_approve_requires_pending_review_or_explicit_partial(
    api_client: AsyncClient, seeded_family: SeededFamily, db_session: AsyncSession
) -> None:
    """IN_PROGRESS 下不带 settle_partial 的整单 approve → 409(§3.1)。"""
    a_account, b_account, _b_child = await _setup_two_children(db_session, seeded_family)
    parent_headers = _auth_headers(seeded_family.parent)
    a_headers = _auth_headers(a_account)
    b_headers = _auth_headers(b_account)

    task = await _create_coop_task(api_client, parent_headers, seeded_family)
    await api_client.post(f"/api/v1/scn/task-instances/{task['id']}/start", headers=a_headers)
    # B 加入后保持 JOINED:A 交卷不改变实例状态(非全员已交)
    await api_client.post(f"/api/v1/scn/task-instances/{task['id']}/join", headers=b_headers)
    await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/submit",
        json={"proof_object_key": await _proof_key_for(db_session, seeded_family, a_account)},
        headers=a_headers,
    )
    resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/approve",
        json={"rating": 5}, headers=parent_headers,
    )
    assert resp.status_code == 409, resp.text
    assert "settle_partial" in resp.text


# ---------------------------------------------------------------------------
# 部分通过判退(裁决 Q1 / Q4)
# ---------------------------------------------------------------------------

async def test_partial_settle_full_refund_first_offense(
    api_client: AsyncClient, seeded_family: SeededFamily, db_session: AsyncSession
) -> None:
    """A 交卷 B 未交,判退收尾:B 首犯全额退、**不递增**放弃计数;A 独得全额 XP(交付孩子数=1)。"""
    a_account, b_account, b_child = await _setup_two_children(db_session, seeded_family)
    parent_headers = _auth_headers(seeded_family.parent)
    a_headers = _auth_headers(a_account)
    b_headers = _auth_headers(b_account)

    task = await _create_coop_task(api_client, parent_headers, seeded_family)
    await api_client.post(f"/api/v1/scn/task-instances/{task['id']}/start", headers=a_headers)
    await api_client.post(f"/api/v1/scn/task-instances/{task['id']}/join", headers=b_headers)
    await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/submit",
        json={"proof_object_key": await _proof_key_for(db_session, seeded_family, a_account)},
        headers=a_headers,
    )

    await db_session.refresh(seeded_family.child)
    await db_session.refresh(b_child)
    a_before = seeded_family.child.time_coin_balance
    b_before = b_child.time_coin_balance
    b_xp_before = b_child.xp
    abandon_before = b_child.daily_abandon_count
    resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/approve",
        json={"rating": 5, "settle_partial": True}, headers=parent_headers,
    )
    assert resp.status_code == 200, resp.text
    detail = resp.json()["data"]
    assert detail["status"] == TaskStatus.COMPLETED.value

    roles = await _statuses(db_session, task["id"])
    assert roles[TaskParticipantRole.OWNER] == TaskParticipantStatus.DONE
    assert roles[TaskParticipantRole.MEMBER] == TaskParticipantStatus.QUIT

    await db_session.refresh(seeded_family.child)
    await db_session.refresh(b_child)
    assert seeded_family.child.time_coin_balance == a_before + 10   # A 退份额
    assert b_child.time_coin_balance == b_before + 10               # 首犯全额退
    assert b_child.daily_abandon_count == abandon_before            # 判退不递增(裁决 Q1)

    # Q4:A 独得全额 XP,B 不分
    task_row = await task_service.get_task(db_session, task["id"])
    expected_xp = xp_service.calculate_xp(
        50, rating=5, started_at=task_row.started_at, submitted_at=task_row.submitted_at,
    )
    assert seeded_family.child.xp == expected_xp
    assert b_child.xp == b_xp_before

    # B 收到判退通知(退款解释)
    assert len(await _notifications(db_session, b_account.id, NotificationType.COOP_PARTIAL_SETTLED)) == 1

    # 流水 note 前缀与全额中性文案(docs/13 §5)
    from app.models.scn_time_coin_log import ScnTimeCoinLog

    notes = (
        await db_session.execute(
            select(ScnTimeCoinLog).where(
                ScnTimeCoinLog.child_id == b_child.id,
                ScnTimeCoinLog.type == CoinTransactionType.TASK_REFUND,
            )
        )
    ).scalars().all()
    assert any(n.note and "[部分通过判退]" in n.note and "全额退还" in n.note for n in notes)


async def test_partial_settle_discount_for_repeat_offender(
    api_client: AsyncClient, seeded_family: SeededFamily, db_session: AsyncSession
) -> None:
    """B 当日已放弃 3 次:判退按 60% 退 + ABANDON_PENALTY,放弃计数不变。"""
    a_account, b_account, b_child = await _setup_two_children(db_session, seeded_family)
    b_child.daily_abandon_count = 3
    await db_session.commit()
    parent_headers = _auth_headers(seeded_family.parent)
    a_headers = _auth_headers(a_account)
    b_headers = _auth_headers(b_account)

    task = await _create_coop_task(api_client, parent_headers, seeded_family)
    await api_client.post(f"/api/v1/scn/task-instances/{task['id']}/start", headers=a_headers)
    await api_client.post(f"/api/v1/scn/task-instances/{task['id']}/join", headers=b_headers)
    await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/submit",
        json={"proof_object_key": await _proof_key_for(db_session, seeded_family, a_account)},
        headers=a_headers,
    )

    await db_session.refresh(b_child)
    b_before = b_child.time_coin_balance
    resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/approve",
        json={"rating": 4, "settle_partial": True}, headers=parent_headers,
    )
    assert resp.status_code == 200, resp.text

    await db_session.refresh(b_child)
    assert b_child.time_coin_balance == b_before + 6   # 10 × 60%
    assert b_child.daily_abandon_count == 3            # 不递增

    from app.models.scn_time_coin_log import ScnTimeCoinLog

    penalty = (
        await db_session.execute(
            select(ScnTimeCoinLog).where(
                ScnTimeCoinLog.child_id == b_child.id,
                ScnTimeCoinLog.type == CoinTransactionType.ABANDON_PENALTY,
            )
        )
    ).scalars().all()
    assert any(t.amount == -4 and "[部分通过判退]" in (t.note or "") for t in penalty)


# ---------------------------------------------------------------------------
# leave(主动放弃:递增计数)
# ---------------------------------------------------------------------------

async def test_leave_increments_abandon_count_owner_blocked(
    api_client: AsyncClient, seeded_family: SeededFamily, db_session: AsyncSession
) -> None:
    """B leave:按当日次数退(首犯全额)并**递增**计数;OWNER 不可 leave。"""
    a_account, b_account, b_child = await _setup_two_children(db_session, seeded_family)
    parent_headers = _auth_headers(seeded_family.parent)
    a_headers = _auth_headers(a_account)
    b_headers = _auth_headers(b_account)

    task = await _create_coop_task(api_client, parent_headers, seeded_family)
    await api_client.post(f"/api/v1/scn/task-instances/{task['id']}/start", headers=a_headers)
    await api_client.post(f"/api/v1/scn/task-instances/{task['id']}/join", headers=b_headers)

    # OWNER 不能 leave(走整体 abandon)
    resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/leave", headers=a_headers
    )
    assert resp.status_code == 409, resp.text

    await db_session.refresh(b_child)
    b_before = b_child.time_coin_balance
    abandon_before = b_child.daily_abandon_count
    resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/leave", headers=b_headers
    )
    assert resp.status_code == 200, resp.text
    roles = await _statuses(db_session, task["id"])
    assert roles[TaskParticipantRole.MEMBER] == TaskParticipantStatus.QUIT

    await db_session.refresh(b_child)
    assert b_child.time_coin_balance == b_before + 10          # 首犯全额退
    assert b_child.daily_abandon_count == abandon_before + 1   # 主动放弃:递增(§5)

    # 实例仍在 IN_PROGRESS,A 可继续交卷并判退收尾
    await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/submit",
        json={"proof_object_key": await _proof_key_for(db_session, seeded_family, a_account, "after")},
        headers=a_headers,
    )
    # B 已 QUIT,A 交卷即全员已交 → 直接 PENDING_REVIEW,整单审批收尾
    resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/approve",
        json={"rating": 5}, headers=parent_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == TaskStatus.COMPLETED.value


# ---------------------------------------------------------------------------
# reject(§3.1)
# ---------------------------------------------------------------------------

async def test_reject_resets_submitted_participants_and_keeps_proofs(
    api_client: AsyncClient, seeded_family: SeededFamily, db_session: AsyncSession
) -> None:
    """reject:SUBMITTED → JOINED、proof 保留;重交后可再审批聚合 COMPLETED。"""
    a_account, b_account, _b_child = await _setup_two_children(db_session, seeded_family)
    parent_headers = _auth_headers(seeded_family.parent)
    a_headers = _auth_headers(a_account)
    b_headers = _auth_headers(b_account)

    task = await _create_coop_task(api_client, parent_headers, seeded_family)
    await api_client.post(f"/api/v1/scn/task-instances/{task['id']}/start", headers=a_headers)
    await api_client.post(f"/api/v1/scn/task-instances/{task['id']}/join", headers=b_headers)
    a_key = await _proof_key_for(db_session, seeded_family, a_account, "a")
    b_key = await _proof_key_for(db_session, seeded_family, b_account, "b")
    await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/submit", json={"proof_object_key": a_key},
        headers=a_headers,
    )
    await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/submit", json={"proof_object_key": b_key},
        headers=b_headers,
    )
    detail = (await api_client.get(
        f"/api/v1/scn/task-instances/{task['id']}", headers=parent_headers)
    ).json()["data"]
    assert detail["status"] == TaskStatus.PENDING_REVIEW.value

    resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/reject",
        json={"comment": "重做"}, headers=parent_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == TaskStatus.IN_PROGRESS.value
    assert await _statuses(db_session, task["id"]) == {
        TaskParticipantRole.OWNER: TaskParticipantStatus.JOINED,
        TaskParticipantRole.MEMBER: TaskParticipantStatus.JOINED,
    }

    # proof 保留(审计链):两条证据仍可读出
    proofs = (await api_client.get(
        f"/api/v1/scn/task-instances/{task['id']}/proofs", headers=parent_headers)
    ).json()["data"]
    assert {p["uploaded_by"] for p in proofs} == {a_account.id, b_account.id}

    # 押金未动
    await db_session.refresh(seeded_family.child)
    # (余额校验在重交审批后统一做,这里只验证子状态与 proof)

    # 重交 → PENDING_REVIEW → 整单审批 COMPLETED
    await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/submit",
        json={"proof_object_key": await _proof_key_for(db_session, seeded_family, a_account, "a2")},
        headers=a_headers,
    )
    await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/submit",
        json={"proof_object_key": await _proof_key_for(db_session, seeded_family, b_account, "b2")},
        headers=b_headers,
    )
    resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/approve",
        json={"rating": 5}, headers=parent_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == TaskStatus.COMPLETED.value
    await db_session.refresh(seeded_family.child)
    await db_session.refresh(await _b_child_of(db_session, b_account))
    assert seeded_family.child.time_coin_balance == 100  # 各退各的份额
    assert (await _b_child_of(db_session, b_account)).time_coin_balance == 100


async def _b_child_of(db_session: AsyncSession, account):
    from app.models.sys_child import SysChild

    return (
        await db_session.execute(select(SysChild).where(SysChild.account_id == account.id))
    ).scalar_one()


# ---------------------------------------------------------------------------
# Q3 家长交付走 proof + Q4 家长不入分母
# ---------------------------------------------------------------------------

async def test_parent_submits_proof_and_excluded_from_xp_denominator(
    api_client: AsyncClient, seeded_family: SeededFamily, db_session: AsyncSession
) -> None:
    """亲子协作:家长提交走 proof(uploaded_by=家长账号,前端据此标"家长代交");
    XP 分母 = 交付孩子数(1)——家长不入分母,孩子拿全额。"""
    a_account, _b_account, _b_child = await _setup_two_children(db_session, seeded_family)
    parent_headers = _auth_headers(seeded_family.parent)
    a_headers = _auth_headers(a_account)

    task = await _create_coop_task(
        api_client, parent_headers, seeded_family, target_child_id=seeded_family.child.id
    )
    await api_client.post(f"/api/v1/scn/task-instances/{task['id']}/start", headers=a_headers)
    resp = await api_client.post(f"/api/v1/scn/task-instances/{task['id']}/join", headers=parent_headers)
    assert resp.status_code == 200, resp.text

    # 家长代交(裁决 Q3)
    resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/submit",
        json={"proof_object_key": await _proof_key_for(db_session, seeded_family, seeded_family.parent, "pa")},
        headers=parent_headers,
    )
    assert resp.status_code == 200, resp.text
    await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/submit",
        json={"proof_object_key": await _proof_key_for(db_session, seeded_family, a_account, "a")},
        headers=a_headers,
    )
    detail = (await api_client.get(
        f"/api/v1/scn/task-instances/{task['id']}", headers=parent_headers)
    ).json()["data"]
    assert detail["status"] == TaskStatus.PENDING_REVIEW.value
    by_account = {p["role"]: p for p in detail["participants"]}
    assert by_account["PARENT"]["participant_status"] == TaskParticipantStatus.SUBMITTED.value

    # proofs 透出 uploaded_by(家长代交标注的序列化基础)
    proofs = (await api_client.get(
        f"/api/v1/scn/task-instances/{task['id']}/proofs", headers=parent_headers)
    ).json()["data"]
    uploaded_by = {p["uploaded_by"] for p in proofs}
    assert seeded_family.parent.id in uploaded_by
    assert a_account.id in uploaded_by

    resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/approve",
        json={"rating": 5}, headers=parent_headers,
    )
    assert resp.status_code == 200, resp.text
    detail = resp.json()["data"]
    assert detail["status"] == TaskStatus.COMPLETED.value

    task_row = await task_service.get_task(db_session, task["id"])
    expected_xp = xp_service.calculate_xp(
        50, rating=5, started_at=task_row.started_at, submitted_at=task_row.submitted_at,
    )
    await db_session.refresh(seeded_family.child)
    assert seeded_family.child.xp == expected_xp  # 全额:分母=1 个孩子(裁决 Q4)
    assert by_account_role(detail, "PARENT")["xp_awarded"] is None


def by_account_role(detail: dict, role: str) -> dict:
    return next(p for p in detail["participants"] if p["role"] == role)


# ---------------------------------------------------------------------------
# 过期(块 F 既定口径:COOP 全额退,不复活)
# ---------------------------------------------------------------------------

async def test_coop_expire_full_refund_and_no_revive(
    api_client: AsyncClient, seeded_family: SeededFamily, db_session: AsyncSession
) -> None:
    """COOP 过期:全员全额退份额、不计放弃惩罚;实例 EXPIRED 终态(不复活,§7)。"""
    a_account, b_account, b_child = await _setup_two_children(db_session, seeded_family)
    parent_headers = _auth_headers(seeded_family.parent)
    a_headers = _auth_headers(a_account)

    b_headers = _auth_headers(b_account)
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    task = await _create_coop_task(api_client, parent_headers, seeded_family, expire_at=past)
    await api_client.post(f"/api/v1/scn/task-instances/{task['id']}/start", headers=a_headers)
    await api_client.post(f"/api/v1/scn/task-instances/{task['id']}/join", headers=b_headers)

    await db_session.refresh(seeded_family.child)
    await db_session.refresh(b_child)
    a_before = seeded_family.child.time_coin_balance
    b_before = b_child.time_coin_balance
    abandon_before = b_child.daily_abandon_count

    processed = await task_service.expire_overdue_tasks(db_session)
    assert processed >= 1
    task_row = await task_service.get_task(db_session, task["id"])
    assert task_row.status == TaskStatus.EXPIRED

    await db_session.refresh(seeded_family.child)
    await db_session.refresh(b_child)
    assert seeded_family.child.time_coin_balance == a_before + 10
    assert b_child.time_coin_balance == b_before + 10
    assert b_child.daily_abandon_count == abandon_before
    # 参与者行保留(EXPIRED 终态,审计不复活)
    roles = await _statuses(db_session, task["id"])
    assert len(roles) == 2
