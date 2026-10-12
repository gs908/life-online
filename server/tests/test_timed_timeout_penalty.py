"""限时任务超时扣半测试(DEV-34 块 D:执行中超时退 50% / 罚 50%)。

覆盖验收要点:
- 已接取(IN_PROGRESS)且 expire_at 已过:状态 EXPIRED,退押金 50%、
  其余 50% 记 TIMEOUT_PENALTY 扣罚,不计入连续放弃,发 TASK_EXPIRED 通知;
- 未接取(AVAILABLE)超时:直接 EXPIRED,无任何押金动作(无 TASK_DEPOSIT 之外的流水);
- 非限时任务(expire_at IS NULL):不参与过期;
- 创建时押金解析落库(耗时驱动),难度只改 XP 不改押金(审批路径集成验证)。

需要可连接的数据库(远程优先),不可达时用例被 `db_ready` fixture 跳过。
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dev.seed import SeededFamily
from app.models.enums import CoinTransactionType, NotificationType, TaskStatus
from app.models.scn_notification import ScnNotification
from app.models.scn_time_coin_log import ScnTimeCoinLog
from app.services import auth_service, task_service

pytestmark = pytest.mark.db


def _auth_headers(account) -> dict[str, str]:
    tokens = auth_service.issue_token_pair(account)
    return {"Authorization": f"Bearer {tokens.access_token}"}


async def _top_up(db_session: AsyncSession, seeded_family: SeededFamily, amount: int = 100) -> None:
    seeded_family.child.time_coin_balance = amount
    await db_session.commit()


async def _create_task(
    api_client: AsyncClient, parent_headers: dict[str, str], seeded_family: SeededFamily, **overrides
) -> dict:
    """默认 DAILY + 30 分钟预计耗时 -> 押金解析为 10(公式落库,不写死)。"""
    body = {
        "season_id": seeded_family.season.id,
        "title": "限时任务",
        "xp_reward": 50,
        "type": "DAILY",
        "estimated_minutes": 30,
        "target_child_id": seeded_family.child.id,
        **overrides,
    }
    resp = await api_client.post("/api/v1/scn/task-instances", json=body, headers=parent_headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


async def _coin_log_types(db_session: AsyncSession, task_id: str) -> list[CoinTransactionType]:
    rows = (await db_session.execute(
        select(ScnTimeCoinLog).where(ScnTimeCoinLog.task_instance_id == task_id)
    )).scalars().all()
    return [r.type for r in rows]


async def _task_notifications(db_session: AsyncSession, task_id: str) -> list[ScnNotification]:
    rows = (await db_session.execute(
        select(ScnNotification).where(ScnNotification.type == NotificationType.TASK_EXPIRED)
    )).scalars().all()
    return [n for n in rows if n.payload.get("task_instance_id") == task_id]


async def test_in_progress_timeout_refunds_half_and_penalizes_half(
    api_client: AsyncClient, seeded_family: SeededFamily, db_session: AsyncSession
) -> None:
    """IN_PROGRESS 超时:退 5 罚 5,coin_delta=-5,不计放弃,通知孩子。"""
    await _top_up(db_session, seeded_family)
    parent_headers = _auth_headers(seeded_family.parent)
    child_headers = _auth_headers(seeded_family.child_account)
    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()

    task = await _create_task(api_client, parent_headers, seeded_family, expire_at=past)
    assert task["time_deposit"] == 10  # 创建时已解析落库(DAILY + 30 分钟 -> 10)

    start_resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/start", headers=child_headers
    )
    assert start_resp.status_code == 200
    await db_session.refresh(seeded_family.child)
    balance_after_start = seeded_family.child.time_coin_balance
    assert balance_after_start == 90  # 100 - 押金 10

    processed = await task_service.expire_overdue_tasks(db_session)
    assert processed >= 1  # 共享开发库上其他家庭可能有同类过期任务,只保证本任务被处理

    expired = await task_service.get_task(db_session, task["id"])
    assert expired.status == TaskStatus.EXPIRED
    assert expired.coin_delta == -5  # 退 5 罚 5,净 -5

    await db_session.refresh(seeded_family.child)
    assert seeded_family.child.time_coin_balance == balance_after_start + 5  # 95
    assert seeded_family.child.daily_abandon_count == 0  # 超时不是主动放弃

    log_types = await _coin_log_types(db_session, task["id"])
    assert CoinTransactionType.TASK_DEPOSIT in log_types
    assert CoinTransactionType.TASK_REFUND in log_types
    assert CoinTransactionType.TIMEOUT_PENALTY in log_types
    assert CoinTransactionType.ABANDON_PENALTY not in log_types  # 不走放弃惩罚路径

    notifications = await _task_notifications(db_session, task["id"])
    assert len(notifications) == 1
    assert notifications[0].recipient_account_id == seeded_family.child_account.id


async def test_available_timeout_expires_without_deposit_actions(
    api_client: AsyncClient, seeded_family: SeededFamily, db_session: AsyncSession
) -> None:
    """AVAILABLE 超时:直接 EXPIRED,未扣押金就无退还/扣罚,余额不动。"""
    await _top_up(db_session, seeded_family)
    parent_headers = _auth_headers(seeded_family.parent)
    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()

    task = await _create_task(api_client, parent_headers, seeded_family, expire_at=past)

    processed = await task_service.expire_overdue_tasks(db_session)
    assert processed >= 1  # 同上,只保证本任务被处理

    expired = await task_service.get_task(db_session, task["id"])
    assert expired.status == TaskStatus.EXPIRED
    assert expired.coin_delta == 0

    await db_session.refresh(seeded_family.child)
    assert seeded_family.child.time_coin_balance == 100  # 未接取,余额分文未动

    log_types = await _coin_log_types(db_session, task["id"])
    assert log_types == []  # 无任何押金流水

    # 通知发给创建任务的家长(未接取,孩子不是当事人)
    notifications = await _task_notifications(db_session, task["id"])
    assert len(notifications) == 1
    assert notifications[0].recipient_account_id == seeded_family.parent.id


async def test_non_timed_task_not_expired(
    api_client: AsyncClient, seeded_family: SeededFamily, db_session: AsyncSession
) -> None:
    """expire_at 为空(非限时)不参与过期,状态保持。"""
    await _top_up(db_session, seeded_family)
    parent_headers = _auth_headers(seeded_family.parent)
    child_headers = _auth_headers(seeded_family.child_account)

    task = await _create_task(api_client, parent_headers, seeded_family)  # 无 deadline/expire_at
    # 用列查询看 expire_at,不在 start 前把 ORM 实例加载进本 session 的身份映射,
    # 否则后续 get_task 读到的是 start 之前的旧内存态(见 test_task_state_machine 的同类注释)。
    from app.models.scn_task_instance import ScnTaskInstance
    expire_at = (await db_session.execute(
        select(ScnTaskInstance.expire_at).where(ScnTaskInstance.id == task["id"])
    )).scalar_one()
    assert expire_at is None

    start_resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/start", headers=child_headers
    )
    assert start_resp.status_code == 200

    # 批处理跑一遍(返回值是全局计数,共享开发库上不可做精确断言),本任务必须保持
    await task_service.expire_overdue_tasks(db_session)
    still = await task_service.get_task(db_session, task["id"])
    assert still.status == TaskStatus.IN_PROGRESS


async def test_difficulty_changes_xp_but_not_deposit(
    api_client: AsyncClient, seeded_family: SeededFamily, db_session: AsyncSession
) -> None:
    """难度 1 与 5 的同参数任务:押金相同(10),审批后 XP 不同(rating=3:50 vs 77)。"""
    await _top_up(db_session, seeded_family, amount=1000)
    parent_headers = _auth_headers(seeded_family.parent)
    child_headers = _auth_headers(seeded_family.child_account)

    from uuid import uuid4

    from app.models.enums import UploadPurpose
    from app.models.sys_upload import SysUpload

    async def _proof(label: str) -> str:
        key = f"proofs/{seeded_family.child_account.id}/{uuid4().hex}-{label}.jpg"
        db_session.add(SysUpload(
            family_id=seeded_family.family.id,
            uploader_account_id=seeded_family.child_account.id,
            storage_provider="local", object_key=key, bucket="local",
            public_url=f"/api/v1/files/{key}",
            content_type="image/jpeg", size=1, purpose=UploadPurpose.TASK_PROOF,
        ))
        await db_session.commit()
        return key

    async def _run(difficulty: int) -> tuple[int, int]:
        task = await _create_task(
            api_client, parent_headers, seeded_family, difficulty=difficulty, title=f"难度{difficulty}"
        )
        await api_client.post(f"/api/v1/scn/task-instances/{task['id']}/start", headers=child_headers)
        await api_client.post(
            f"/api/v1/scn/task-instances/{task['id']}/submit",
            json={"proof_object_key": await _proof(f"d{difficulty}")},
            headers=child_headers,
        )
        resp = await api_client.post(
            f"/api/v1/scn/task-instances/{task['id']}/approve",
            json={"rating": 3},
            headers=parent_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        return data["time_deposit"], data["xp_awarded"]

    deposit_low, xp_low = await _run(1)
    deposit_high, xp_high = await _run(5)
    assert deposit_low == deposit_high == 10  # 难度不改押金
    # xp = 50 x rating3(1.0) x 难度(0.9 / 1.4) x speed_bonus(1.1,提交紧接接取,窗口内)
    assert xp_low == 50   # round(50 * 0.9 * 1.1)
    assert xp_high == 77  # round(50 * 1.4 * 1.1)


async def test_library_suggested_deposit_seeds_resolution(
    api_client: AsyncClient, seeded_family: SeededFamily, db_session: AsyncSession
) -> None:
    """模板库套用:suggested_time_deposit 作为显式值参与解析(死字段激活)。"""
    from app.models.enums import TaskCategory
    from app.models.scn_task_template_library import ScnTaskTemplateLibrary

    library = ScnTaskTemplateLibrary(
        family_id=seeded_family.family.id,
        category=TaskCategory.CHORE,
        title="库模板-洗碗",
        suggested_xp=50,
        suggested_time_deposit=18,  # DAILY 范围 5-20 内
        suggested_type="DAILY",
    )
    db_session.add(library)
    await db_session.commit()

    parent_headers = _auth_headers(seeded_family.parent)
    task = await _create_task(
        api_client, parent_headers, seeded_family, library_id=library.id, title="套用库模板"
    )
    assert task["time_deposit"] == 18

    # 越界建议值仍被 clamp:建议 99 -> 20(DAILY 上限)
    library.suggested_time_deposit = 99
    await db_session.commit()
    task2 = await _create_task(
        api_client, parent_headers, seeded_family, library_id=library.id, title="套用越界库模板"
    )
    assert task2["time_deposit"] == 20
