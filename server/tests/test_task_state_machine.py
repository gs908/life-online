"""任务状态机闭环测试(DEV-8;DEV-36 块 F 扩链式与协作用例)。

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
- CHAIN 递进串行(DEV-36):链首投放/逐步解锁/链末 XP 加成/中断不回退可续做/建链校验。
- COOP 多参与者协作(DEV-36):押金动态均摊、XP 均摊、亲子参与、join 校验、放弃结算。

需要可连接的数据库(远程优先),不可达时该模块内用例会被 `db_ready` fixture 跳过。
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.dev.seed import SeededFamily, cleanup_family, seed_basic_family
from app.models.enums import TaskStatus
from app.models.scn_task_instance import ScnTaskInstance
from app.services import auth_service, task_service
from app.services.task_service import REJECT_RESUBMIT_GRACE

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


async def _proof_key(db_session: AsyncSession, seeded_family: SeededFamily, label: str = "p") -> str:
    """为接取孩子造一条真实归属的 task_proof 上传记录。

    DEV-20 起 submit 校验 proof_object_key 归属(存在 + uploader=当前孩子 +
    purpose=task_proof),测试不再能用裸字符串 "proofs/1.jpg" 蒙混。
    """
    from uuid import uuid4

    from app.models.enums import UploadPurpose
    from app.models.sys_upload import SysUpload

    key = f"proofs/{seeded_family.child_account.id}/{uuid4().hex}-{label}.jpg"
    db_session.add(SysUpload(
        family_id=seeded_family.family.id,
        uploader_account_id=seeded_family.child_account.id,
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
        json={"proof_object_key": await _proof_key(db_session, seeded_family, "1")},
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
        json={"proof_object_key": await _proof_key(db_session, seeded_family, "1")},
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
        json={"proof_object_key": await _proof_key(db_session, seeded_family, "2")},
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


async def test_reject_after_deadline_grants_resubmit_window_instead_of_expiring(
    api_client: AsyncClient, seeded_family: SeededFamily, db_session: AsyncSession
) -> None:
    """孩子在截止前提交,但家长审核拖到截止后才驳回:驳回必须补一个重新提交窗口,
    不能让下一轮 expire_overdue_tasks 直接把 IN_PROGRESS 任务判 EXPIRED。"""
    await _top_up(db_session, seeded_family)
    parent_headers = _auth_headers(seeded_family.parent)
    child_headers = _auth_headers(seeded_family.child_account)

    future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    task = await _create_task(api_client, parent_headers, seeded_family, expire_at=future)

    await api_client.post(f"/api/v1/scn/task-instances/{task['id']}/start", headers=child_headers)
    submit_resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/submit",
        json={"proof_object_key": await _proof_key(db_session, seeded_family, "1")},
        headers=child_headers,
    )
    assert submit_resp.status_code == 200  # 截止前提交成功

    # 模拟家长审核拖到截止之后才处理:用一次不经过 ORM 身份映射的裸 UPDATE 把
    # expire_at 拨到过去,而不是真的 sleep 等待,避免测试因时钟精度产生偶发失败;
    # 也避免 db_session 里预先缓存一个旧状态的 ORM 对象,导致后面 get_task 读到
    # 过期的内存态(expire_on_commit=False 下,已加载对象不会被后续查询覆盖)。
    now = datetime.now(UTC)
    await db_session.execute(
        update(ScnTaskInstance)
        .where(ScnTaskInstance.id == task["id"])
        .values(expire_at=now - timedelta(minutes=1))
    )
    await db_session.commit()

    reject_resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/reject",
        json={"comment": "截止后才审到,但内容需要重做"},
        headers=parent_headers,
    )
    assert reject_resp.status_code == 200
    rejected = reject_resp.json()["data"]
    assert rejected["status"] == TaskStatus.IN_PROGRESS.value

    rejected_row = await task_service.get_task(db_session, task["id"])
    assert rejected_row.expire_at is not None
    # 补的窗口必须是 now + REJECT_RESUBMIT_GRACE(24h),而不是随便一个未来时间点;
    # 允许几秒钟的执行耗时误差,否则宽限期意外缩短成很小的正数也会被上面的 `> now` 放过。
    expected_expire_at = now + REJECT_RESUBMIT_GRACE
    assert abs((rejected_row.expire_at - expected_expire_at).total_seconds()) < 60  # 远程 Supabase 往返延迟秒级,放宽断言容差

    # 下一轮过期批处理不应该把这个任务判过期
    processed = await task_service.expire_overdue_tasks(db_session, now=now)
    assert processed == 0
    still_in_progress = await task_service.get_task(db_session, task["id"])
    assert still_in_progress.status == TaskStatus.IN_PROGRESS

    # 孩子在新窗口内可以修改后重新提交,家长再审核通过
    resubmit_resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/submit",
        json={"proof_object_key": await _proof_key(db_session, seeded_family, "2")},
        headers=child_headers,
    )
    assert resubmit_resp.status_code == 200
    assert resubmit_resp.json()["data"]["status"] == TaskStatus.PENDING_REVIEW.value

    approve_resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/approve", json={"rating": 5}, headers=parent_headers
    )
    assert approve_resp.status_code == 200
    assert approve_resp.json()["data"]["status"] == TaskStatus.COMPLETED.value


async def test_reject_resubmit_grace_window_boundary(
    api_client: AsyncClient, seeded_family: SeededFamily, db_session: AsyncSession
) -> None:
    """`REJECT_RESUBMIT_GRACE` 是 24h 而不是任意正数:在 grace 窗口内(now+23h)跑批处理
    不应过期,超出窗口(now+25h)之后必须过期。直接断言批处理行为,而不是只看 `expire_at`
    的字段值,避免过期判定逻辑和字段设置的窗口悄悄不一致。"""
    await _top_up(db_session, seeded_family)
    parent_headers = _auth_headers(seeded_family.parent)
    child_headers = _auth_headers(seeded_family.child_account)

    future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    task = await _create_task(api_client, parent_headers, seeded_family, expire_at=future)

    await api_client.post(f"/api/v1/scn/task-instances/{task['id']}/start", headers=child_headers)
    await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/submit",
        json={"proof_object_key": await _proof_key(db_session, seeded_family, "1")},
        headers=child_headers,
    )

    now = datetime.now(UTC)
    await db_session.execute(
        update(ScnTaskInstance)
        .where(ScnTaskInstance.id == task["id"])
        .values(expire_at=now - timedelta(minutes=1))
    )
    await db_session.commit()

    reject_resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/reject",
        json={"comment": "截止后才审到,补一个新窗口"},
        headers=parent_headers,
    )
    assert reject_resp.status_code == 200

    # 窗口内(23h < 24h grace):批处理不应把它判过期
    processed_within_grace = await task_service.expire_overdue_tasks(
        db_session, now=now + timedelta(hours=23)
    )
    assert processed_within_grace == 0
    still_in_progress = await task_service.get_task(db_session, task["id"])
    assert still_in_progress.status == TaskStatus.IN_PROGRESS

    # 窗口外(25h > 24h grace):批处理必须把它判过期
    processed_past_grace = await task_service.expire_overdue_tasks(
        db_session, now=now + timedelta(hours=25)
    )
    assert processed_past_grace == 1
    expired_row = await task_service.get_task(db_session, task["id"])
    assert expired_row.status == TaskStatus.EXPIRED


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
    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()

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
        json={"proof_object_key": await _proof_key(db_session, seeded_family, "1")},
        headers=child_headers,
    )

    # PENDING_REVIEW 状态下孩子不能再次提交/放弃
    submit_again = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/submit",
        json={"proof_object_key": await _proof_key(db_session, seeded_family, "2")},
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

    # 孩子不能审核/驳回任务(先合法提交进 PENDING_REVIEW)
    await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/submit",
        json={"proof_object_key": await _proof_key(db_session, seeded_family, "perm")},
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


async def test_submit_validates_proof_ownership(
    api_client: AsyncClient, seeded_family: SeededFamily, db_session: AsyncSession
) -> None:
    """DEV-20:submit 的 proof_object_key 必须是当前孩子本人上传的 task_proof 凭证。

    不存在的 key / 他人上传的 key / 非 task_proof 的 key 一律 422;
    合法 key 提交成功。防 local 模式下用任意字符串引用/探测他人对象。
    """
    from uuid import uuid4

    from app.models.enums import UploadPurpose
    from app.models.sys_upload import SysUpload

    await _top_up(db_session, seeded_family)
    parent_headers = _auth_headers(seeded_family.parent)
    child_headers = _auth_headers(seeded_family.child_account)

    task = await _create_task(api_client, parent_headers, seeded_family)
    await api_client.post(f"/api/v1/scn/task-instances/{task['id']}/start", headers=child_headers)

    async def _submit(key: str):
        return await api_client.post(
            f"/api/v1/scn/task-instances/{task['id']}/submit",
            json={"proof_object_key": key},
            headers=child_headers,
        )

    # 1) 不存在的 key
    resp = await _submit(f"proofs/{uuid4().hex}/nonexistent.jpg")
    assert resp.status_code == 422, resp.text

    # 2) 存在但上传者是家长(他人)的 key
    parent_key = f"proofs/{uuid4().hex}-parent.jpg"
    db_session.add(SysUpload(
        family_id=seeded_family.family.id,
        uploader_account_id=seeded_family.parent.id,
        storage_provider="local", object_key=parent_key, bucket="local",
        public_url=f"/api/v1/files/{parent_key}",
        content_type="image/jpeg", size=1, purpose=UploadPurpose.TASK_PROOF,
    ))
    await db_session.commit()
    resp = await _submit(parent_key)
    assert resp.status_code == 422, resp.text

    # 3) 存在、本人上传,但 purpose 不是 task_proof
    avatar_key = f"avatars/{uuid4().hex}.png"
    db_session.add(SysUpload(
        family_id=seeded_family.family.id,
        uploader_account_id=seeded_family.child_account.id,
        storage_provider="local", object_key=avatar_key, bucket="local",
        public_url=f"/api/v1/files/{avatar_key}",
        content_type="image/png", size=1, purpose=UploadPurpose.AVATAR,
    ))
    await db_session.commit()
    resp = await _submit(avatar_key)
    assert resp.status_code == 422, resp.text

    # 4) 合法 key:本人上传的 task_proof
    resp = await _submit(await _proof_key(db_session, seeded_family, "own"))
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == TaskStatus.PENDING_REVIEW.value


# ============================================================================
# CHAIN 递进串行(DEV-36 块 F)
# ============================================================================

from uuid import uuid4

from app.models.enums import TaskType
from app.services import family_service, xp_service


async def _create_chain_step(
    api_client: AsyncClient,
    parent_headers: dict[str, str],
    seeded_family: SeededFamily,
    *,
    chain_key: str,
    order: int,
    total: int,
    title: str,
    xp_reward: int = 50,
    time_deposit: int = 10,
    estimated_minutes: int | None = 120,
    as_instance: bool = False,
) -> dict:
    """创建一个链步。链首走实例接口(投放首步),后续走模板接口(不投放)。"""
    body = {
        "season_id": seeded_family.season.id,
        "title": title,
        "type": TaskType.CHAIN.value,
        "chain_key": chain_key,
        "chain_order": order,
        "chain_total": total,
        "xp_reward": xp_reward,
        "time_deposit": time_deposit,
        "estimated_minutes": estimated_minutes,
        "difficulty": order,  # 递进难度:每步按序配置
        "target_child_id": seeded_family.child.id,
    }
    path = "/api/v1/scn/task-instances" if as_instance else "/api/v1/scn/task-templates"
    resp = await api_client.post(path, json=body, headers=parent_headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


async def _chain_instances(
    db_session: AsyncSession, seeded_family: SeededFamily, chain_key: str
) -> list[ScnTaskInstance]:
    # API 侧(独立 session)提交的状态变化对本 session 的已加载对象不可见
    # (expire_on_commit=False 下已加载对象不会被后续查询覆盖,同 REJECT_RESUBMIT_GRACE
    # 用例的注释)。用 populate_existing 强制本次查询用数据库当前值覆盖内存态。
    from sqlalchemy import select as sa_select
    from sqlalchemy.orm import selectinload

    from app.models.scn_task_template import ScnTaskTemplate

    stmt = (
        sa_select(ScnTaskInstance)
        .join(ScnTaskTemplate, ScnTaskInstance.template_id == ScnTaskTemplate.id)
        .where(
            ScnTaskInstance.family_id == seeded_family.family.id,
            ScnTaskInstance.season_id == seeded_family.season.id,
            ScnTaskTemplate.chain_key == chain_key,
        )
        .options(selectinload(ScnTaskInstance.template))
        .execution_options(populate_existing=True)
    )
    items = list((await db_session.execute(stmt)).scalars().all())
    return sorted(items, key=lambda t: t.chain_index or 0)


async def _complete_step(
    api_client: AsyncClient,
    db_session: AsyncSession,
    seeded_family: SeededFamily,
    task_id: str,
    *,
    rating: int = 5,
) -> dict:
    child_headers = _auth_headers(seeded_family.child_account)
    await api_client.post(f"/api/v1/scn/task-instances/{task_id}/start", headers=child_headers)
    await api_client.post(
        f"/api/v1/scn/task-instances/{task_id}/submit",
        json={"proof_object_key": await _proof_key(db_session, seeded_family, task_id[:8])},
        headers=child_headers,
    )
    approve_resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task_id}/approve",
        json={"rating": rating},
        headers=_auth_headers(seeded_family.parent),
    )
    assert approve_resp.status_code == 200, approve_resp.text
    return approve_resp.json()["data"]


async def test_chain_progressive_unlock_and_final_bonus(
    api_client: AsyncClient, seeded_family: SeededFamily, db_session: AsyncSession
) -> None:
    """链首投放、逐步解锁、链末 XP 加成:审批通过第 N 步才生成第 N+1 步;
    链末步骤的 XP 恰好等于带 chain_final_bonus 的计算值。"""
    await _top_up(db_session, seeded_family, amount=200)
    parent_headers = _auth_headers(seeded_family.parent)
    chain_key = f"chain-{uuid4().hex[:8]}"

    head = await _create_chain_step(
        api_client, parent_headers, seeded_family,
        chain_key=chain_key, order=1, total=3, title="链首", as_instance=True,
    )
    assert head["chain_index"] == 1
    assert head["chain_total"] == 3
    assert head["status"] == TaskStatus.AVAILABLE.value

    await _create_chain_step(api_client, parent_headers, seeded_family,
                             chain_key=chain_key, order=2, total=3, title="第二步")
    await _create_chain_step(api_client, parent_headers, seeded_family,
                             chain_key=chain_key, order=3, total=3, title="链末")

    # 触发时只投放链首步:2/3 步模板存在,但实例只有 1 条
    instances = await _chain_instances(db_session, seeded_family, chain_key)
    assert [t.chain_index for t in instances] == [1]

    step1 = await _complete_step(api_client, db_session, seeded_family, head["id"])
    assert step1["status"] == TaskStatus.COMPLETED.value

    # 第 1 步完成 -> 第 2 步解锁
    instances = await _chain_instances(db_session, seeded_family, chain_key)
    assert [t.chain_index for t in instances] == [1, 2]
    step2_row = instances[1]
    assert step2_row.status == TaskStatus.AVAILABLE
    assert step2_row.expire_at is not None  # estimated_minutes 生效为顺延窗口
    assert instances[0].status == TaskStatus.COMPLETED

    step2 = await _complete_step(api_client, db_session, seeded_family, step2_row.id)
    instances = await _chain_instances(db_session, seeded_family, chain_key)
    step2_after = instances[1]
    expected_step2 = xp_service.calculate_xp(
        50, rating=5,
        started_at=step2_after.started_at, submitted_at=step2_after.submitted_at,
        chain_index=2, chain_total=3,
    )
    assert step2["xp_awarded"] == expected_step2

    # 第 3 步(链末)完成:享受 chain_final_bonus(1.5)
    instances = await _chain_instances(db_session, seeded_family, chain_key)
    step3_row = instances[2]
    step3 = await _complete_step(api_client, db_session, seeded_family, step3_row.id)
    instances = await _chain_instances(db_session, seeded_family, chain_key)
    step3_after = instances[2]
    expected_step3 = xp_service.calculate_xp(
        50, rating=5,
        started_at=step3_after.started_at, submitted_at=step3_after.submitted_at,
        chain_index=3, chain_total=3,
    )
    assert step3["xp_awarded"] == expected_step3
    assert expected_step3 > expected_step2  # 链末加成确实生效

    # 链已走完,不再生成新实例
    assert [t.chain_index for t in instances] == [1, 2, 3]


async def test_chain_interrupt_abandon_does_not_rollback(
    api_client: AsyncClient, seeded_family: SeededFamily, db_session: AsyncSession
) -> None:
    """中断与续做:链内某步放弃不回退整条链——已完成步骤保持 COMPLETED,
    当前步回到 AVAILABLE 可重做,重做完继续从断点解锁下一步。"""
    await _top_up(db_session, seeded_family, amount=200)
    parent_headers = _auth_headers(seeded_family.parent)
    child_headers = _auth_headers(seeded_family.child_account)
    chain_key = f"chain-{uuid4().hex[:8]}"

    head = await _create_chain_step(
        api_client, parent_headers, seeded_family,
        chain_key=chain_key, order=1, total=3, title="链首", as_instance=True,
    )
    await _create_chain_step(api_client, parent_headers, seeded_family,
                             chain_key=chain_key, order=2, total=3, title="第二步")
    await _create_chain_step(api_client, parent_headers, seeded_family,
                             chain_key=chain_key, order=3, total=3, title="链末")

    await _complete_step(api_client, db_session, seeded_family, head["id"])

    instances = await _chain_instances(db_session, seeded_family, chain_key)
    step2_id = instances[1].id

    # 接取第 2 步后放弃:第 1 步保持 COMPLETED,第 2 步回 AVAILABLE,不生成第 3 步
    await api_client.post(f"/api/v1/scn/task-instances/{step2_id}/start", headers=child_headers)
    abandon_resp = await api_client.post(
        f"/api/v1/scn/task-instances/{step2_id}/abandon", headers=child_headers
    )
    assert abandon_resp.status_code == 200

    instances = await _chain_instances(db_session, seeded_family, chain_key)
    assert instances[0].status == TaskStatus.COMPLETED  # 不回退
    assert instances[1].status == TaskStatus.AVAILABLE
    assert len(instances) == 2  # 断点处暂停,没有第 3 步

    # 从断点续做:重新接取并完成第 2 步 -> 第 3 步解锁
    await _complete_step(api_client, db_session, seeded_family, step2_id)
    instances = await _chain_instances(db_session, seeded_family, chain_key)
    assert [t.chain_index for t in instances] == [1, 2, 3]
    assert instances[0].status == TaskStatus.COMPLETED
    assert instances[1].status == TaskStatus.COMPLETED
    assert instances[2].status == TaskStatus.AVAILABLE


async def test_chain_interrupt_expire_does_not_rollback(
    api_client: AsyncClient, seeded_family: SeededFamily, db_session: AsyncSession
) -> None:
    """链内步骤超时过期同样不回退:已完成步骤保持 COMPLETED,当前步 EXPIRED,
    不生成下一步(过期后的顺延/重做由 DEV-35 池规则接手,接合点不变)。"""
    await _top_up(db_session, seeded_family, amount=200)
    parent_headers = _auth_headers(seeded_family.parent)
    child_headers = _auth_headers(seeded_family.child_account)
    chain_key = f"chain-{uuid4().hex[:8]}"

    head = await _create_chain_step(
        api_client, parent_headers, seeded_family,
        chain_key=chain_key, order=1, total=3, title="链首", as_instance=True,
    )
    await _create_chain_step(api_client, parent_headers, seeded_family,
                             chain_key=chain_key, order=2, total=3, title="第二步")

    await _complete_step(api_client, db_session, seeded_family, head["id"])
    instances = await _chain_instances(db_session, seeded_family, chain_key)
    step2_id = instances[1].id

    await api_client.post(f"/api/v1/scn/task-instances/{step2_id}/start", headers=child_headers)
    # 把 expire_at 拨到过去,跑过期批处理(裸 UPDATE,避免 ORM 缓存旧状态)
    now = datetime.now(UTC)
    await db_session.execute(
        update(ScnTaskInstance)
        .where(ScnTaskInstance.id == step2_id)
        .values(expire_at=now - timedelta(minutes=1))
    )
    await db_session.commit()

    processed = await task_service.expire_overdue_tasks(db_session, now=now)
    assert processed >= 1

    instances = await _chain_instances(db_session, seeded_family, chain_key)
    assert instances[0].status == TaskStatus.COMPLETED  # 不回退
    assert instances[1].status == TaskStatus.EXPIRED
    assert len(instances) == 2  # 不生成第 3 步


async def test_chain_creation_validation(
    api_client: AsyncClient, seeded_family: SeededFamily, db_session: AsyncSession
) -> None:
    """建链校验:缺 chain_key / 单步链 / 重复步序 / 直接投放非链首 / 非 CHAIN 带链字段,一律拒绝。"""
    parent_headers = _auth_headers(seeded_family.parent)
    base = {
        "season_id": seeded_family.season.id,
        "title": "非法链",
        "type": TaskType.CHAIN.value,
        "xp_reward": 50,
        "time_deposit": 10,
        "target_child_id": seeded_family.child.id,
    }

    async def _post(body: dict, path: str = "/api/v1/scn/task-instances"):
        return await api_client.post(path, json=body, headers=parent_headers)

    resp = await _post({**base, "chain_order": 1, "chain_total": 3})  # 缺 chain_key
    assert resp.status_code == 422, resp.text

    chain_key = f"chain-{uuid4().hex[:8]}"
    resp = await _post({**base, "chain_key": chain_key, "chain_order": 1, "chain_total": 1})
    assert resp.status_code == 422, resp.text  # 单步链无意义

    ok_resp = await _post({**base, "title": "链首", "chain_key": chain_key,
                           "chain_order": 1, "chain_total": 3})
    assert ok_resp.status_code == 200, ok_resp.text

    resp = await _post({**base, "title": "重复链首", "chain_key": chain_key,
                        "chain_order": 1, "chain_total": 3})
    assert resp.status_code == 409, resp.text  # 同步序重复

    resp = await _post({**base, "title": "直接投放第2步", "chain_key": chain_key,
                        "chain_order": 2, "chain_total": 3})
    assert resp.status_code == 422, resp.text  # 实例接口只投放链首

    resp = await _post({**base, "title": "第2步", "chain_key": chain_key,
                        "chain_order": 2, "chain_total": 3},
                       path="/api/v1/scn/task-templates")
    assert resp.status_code == 200, resp.text  # 模板接口合法

    non_chain = {**base, "title": "日常带链字段", "type": TaskType.DAILY.value, "chain_key": "k"}
    resp = await _post(non_chain)
    assert resp.status_code == 422, resp.text  # 非 CHAIN 不允许链字段


# ============================================================================
# COOP 多参与者协作(DEV-36 块 F)
# ============================================================================


async def _second_child(db_session: AsyncSession, seeded_family: SeededFamily):
    """在已种家庭里再造一个孩子(多孩子协作用),返回 (account, child)。"""
    from sqlalchemy import select as sa_select

    from app.models.sys_child import SysChild

    account = await family_service.create_adventurer(
        db_session, family_id=seeded_family.family.id, name=f"二孩-{uuid4().hex[:4]}"
    )
    child = (
        await db_session.execute(sa_select(SysChild).where(SysChild.account_id == account.id))
    ).scalar_one()
    return account, child


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


async def test_coop_deposit_rebalanced_and_xp_split(
    api_client: AsyncClient, seeded_family: SeededFamily, db_session: AsyncSession
) -> None:
    """两孩子协作:主接取人先垫全额,第二人加入即重新均摊(退差额);
    审批后押金按份额退还、XP 均摊,participants 记录每人份额与所得。"""
    from app.services import coop_service

    await _top_up(db_session, seeded_family, amount=100)
    b_account, b_child = await _second_child(db_session, seeded_family)
    b_child.time_coin_balance = 100
    await db_session.commit()

    parent_headers = _auth_headers(seeded_family.parent)
    a_headers = _auth_headers(seeded_family.child_account)
    b_headers = _auth_headers(b_account)

    task = await _create_coop_task(api_client, parent_headers, seeded_family)

    # A 接取:独自承担全额押金 20
    start_resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/start", headers=a_headers
    )
    assert start_resp.status_code == 200, start_resp.text
    started = start_resp.json()["data"]
    assert [(p["role"], p["deposit_share"]) for p in started["participants"]] == [("OWNER", 20)]

    await db_session.refresh(seeded_family.child)
    assert seeded_family.child.time_coin_balance == 80  # 100 - 20

    # B 加入:重新均摊 -> 各 10,A 即时退差额 10
    join_resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/join", headers=b_headers
    )
    assert join_resp.status_code == 200, join_resp.text
    joined = join_resp.json()["data"]
    assert sorted((p["role"], p["deposit_share"]) for p in joined["participants"]) == [
        ("MEMBER", 10), ("OWNER", 10),
    ]

    await db_session.refresh(seeded_family.child)
    await db_session.refresh(b_child)
    assert seeded_family.child.time_coin_balance == 90  # 80 + 退 10
    assert b_child.time_coin_balance == 90  # 100 - 10

    # A 提交,家长审批:押金按份额退,XP 均摊
    submit_resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/submit",
        json={"proof_object_key": await _proof_key(db_session, seeded_family, "coop")},
        headers=a_headers,
    )
    assert submit_resp.status_code == 200

    a_xp_before = seeded_family.child.xp
    b_xp_before = b_child.xp
    approve_resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/approve",
        json={"rating": 5}, headers=parent_headers,
    )
    assert approve_resp.status_code == 200, approve_resp.text
    approved = approve_resp.json()["data"]
    assert approved["status"] == TaskStatus.COMPLETED.value

    task_row = await task_service.get_task(db_session, task["id"])
    expected_total_xp = xp_service.calculate_xp(
        50, rating=5, started_at=task_row.started_at, submitted_at=task_row.submitted_at,
    )
    assert approved["xp_awarded"] == expected_total_xp
    shares = coop_service.split_evenly(expected_total_xp, 2)

    await db_session.refresh(seeded_family.child)
    await db_session.refresh(b_child)
    assert seeded_family.child.xp == a_xp_before + shares[0]  # OWNER 先加入,拿前一份
    assert b_child.xp == b_xp_before + shares[1]
    assert shares[0] + shares[1] == expected_total_xp

    # 押金各退各的份额,双方回 100
    assert seeded_family.child.time_coin_balance == 100
    assert b_child.time_coin_balance == 100

    # participants 落了每人份额与 XP
    detail_resp = await api_client.get(
        f"/api/v1/scn/task-instances/{task['id']}", headers=parent_headers
    )
    participants = {p["role"]: p for p in detail_resp.json()["data"]["participants"]}
    assert participants["OWNER"]["deposit_share"] == 10
    assert participants["MEMBER"]["deposit_share"] == 10
    assert participants["OWNER"]["xp_awarded"] == shares[0]
    assert participants["MEMBER"]["xp_awarded"] == shares[1]


async def test_coop_parent_participates_without_wallet(
    api_client: AsyncClient, seeded_family: SeededFamily, db_session: AsyncSession
) -> None:
    """亲子协作:家长以 PARENT 角色加入,不动钱包、不占押金/XP 份额;
    孩子照常拿全额 XP、全额押金结算。"""
    await _top_up(db_session, seeded_family, amount=100)
    parent_headers = _auth_headers(seeded_family.parent)
    a_headers = _auth_headers(seeded_family.child_account)

    task = await _create_coop_task(
        api_client, parent_headers, seeded_family, target_child_id=seeded_family.child.id
    )
    await api_client.post(f"/api/v1/scn/task-instances/{task['id']}/start", headers=a_headers)

    join_resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/join", headers=parent_headers
    )
    assert join_resp.status_code == 200, join_resp.text
    joined = join_resp.json()["data"]
    roles = {p["role"]: p for p in joined["participants"]}
    assert set(roles) == {"OWNER", "PARENT"}
    assert roles["PARENT"]["deposit_share"] == 0
    assert roles["PARENT"]["child_id"] is None

    await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/submit",
        json={"proof_object_key": await _proof_key(db_session, seeded_family, "pk")},
        headers=a_headers,
    )
    approve_resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/approve",
        json={"rating": 4}, headers=parent_headers,
    )
    assert approve_resp.status_code == 200

    task_row = await task_service.get_task(db_session, task["id"])
    expected_xp = xp_service.calculate_xp(
        50, rating=4, started_at=task_row.started_at, submitted_at=task_row.submitted_at,
    )

    detail_resp = await api_client.get(
        f"/api/v1/scn/task-instances/{task['id']}", headers=parent_headers
    )
    participants = {p["role"]: p for p in detail_resp.json()["data"]["participants"]}
    assert participants["OWNER"]["xp_awarded"] == expected_xp  # 全额给孩子,家长不分
    assert participants["PARENT"]["xp_awarded"] is None
    assert participants["PARENT"]["deposit_share"] == 0


async def test_coop_join_validation(
    api_client: AsyncClient, seeded_family: SeededFamily,
    other_family: SeededFamily, db_session: AsyncSession,
) -> None:
    """join 校验:非 COOP 拒绝 / 未开始 409 / 重复加入 409 / 余额不足 422 / 跨家庭 403。"""
    await _top_up(db_session, seeded_family, amount=100)
    b_account, b_child = await _second_child(db_session, seeded_family)
    b_child.time_coin_balance = 5  # 不够 10 的份额
    await db_session.commit()

    parent_headers = _auth_headers(seeded_family.parent)
    a_headers = _auth_headers(seeded_family.child_account)
    b_headers = _auth_headers(b_account)

    # 非 COOP 任务不能加入
    daily = await _create_task(api_client, parent_headers, seeded_family)
    resp = await api_client.post(f"/api/v1/scn/task-instances/{daily['id']}/join", headers=b_headers)
    assert resp.status_code == 422, resp.text

    coop = await _create_coop_task(api_client, parent_headers, seeded_family)

    # AVAILABLE(主接取人未 start)不能加入
    resp = await api_client.post(f"/api/v1/scn/task-instances/{coop['id']}/join", headers=b_headers)
    assert resp.status_code == 409, resp.text

    # 跨家庭加入
    other_child_headers = _auth_headers(other_family.child_account)
    resp = await api_client.post(
        f"/api/v1/scn/task-instances/{coop['id']}/join", headers=other_child_headers
    )
    assert resp.status_code == 403, resp.text

    await api_client.post(f"/api/v1/scn/task-instances/{coop['id']}/start", headers=a_headers)

    # 余额不足(份额 10 > 余额 5)
    resp = await api_client.post(f"/api/v1/scn/task-instances/{coop['id']}/join", headers=b_headers)
    assert resp.status_code == 422, resp.text

    # 主接取人(A)不能重复以 join 方式加入(已是 OWNER 参与者)
    resp = await api_client.post(f"/api/v1/scn/task-instances/{coop['id']}/join", headers=a_headers)
    assert resp.status_code == 409, resp.text

    # 补足余额后加入成功,再重复加入 -> 409
    b_child.time_coin_balance = 50
    await db_session.commit()
    resp = await api_client.post(f"/api/v1/scn/task-instances/{coop['id']}/join", headers=b_headers)
    assert resp.status_code == 200, resp.text
    resp = await api_client.post(f"/api/v1/scn/task-instances/{coop['id']}/join", headers=b_headers)
    assert resp.status_code == 409, resp.text


async def test_coop_abandon_refunds_shares_and_clears_participants(
    api_client: AsyncClient, seeded_family: SeededFamily, db_session: AsyncSession
) -> None:
    """COOP 放弃:发起者按连续放弃规则结算,其他参与者全额退份额且不计惩罚;
    参与者行清除,任务回 AVAILABLE 可重新组队。"""
    await _top_up(db_session, seeded_family, amount=100)
    b_account, b_child = await _second_child(db_session, seeded_family)
    b_child.time_coin_balance = 100
    await db_session.commit()

    parent_headers = _auth_headers(seeded_family.parent)
    a_headers = _auth_headers(seeded_family.child_account)
    b_headers = _auth_headers(b_account)

    task = await _create_coop_task(api_client, parent_headers, seeded_family)
    await api_client.post(f"/api/v1/scn/task-instances/{task['id']}/start", headers=a_headers)
    join_resp = await api_client.post(f"/api/v1/scn/task-instances/{task['id']}/join", headers=b_headers)
    assert join_resp.status_code == 200

    abandon_resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/abandon", headers=a_headers
    )
    assert abandon_resp.status_code == 200, abandon_resp.text
    abandoned = abandon_resp.json()["data"]
    assert abandoned["status"] == TaskStatus.AVAILABLE.value
    assert abandoned["participants"] == []  # 参与者清除,可重新组队

    # 双方各退份额 10(A 当日放弃次数 0,全额);B 不计放弃惩罚
    await db_session.refresh(seeded_family.child)
    await db_session.refresh(b_child)
    assert seeded_family.child.time_coin_balance == 100
    assert b_child.time_coin_balance == 100
    assert seeded_family.child.daily_abandon_count == 1
    assert b_child.daily_abandon_count == 0
