"""多证据提交测试(DEV-33 块 E / DEV-37)。

分层语义:sys_upload 退为通用文件台账;scn_task_proof 是任务证据表,
提交时按所选文件创建,kind 由 content_type 推导。

覆盖(docs/12 §5.5 验收用例):
- 多 key 提交成功;TaskRead.proofs 返回全部证据,proof_url = 首个(过渡);
  scn_task_proof 行与 sys_upload 一一对应。
- 跨用户 key 拒绝;超数量(max_proof_files)拒绝;被其他任务占用的 key 拒绝。
- 读取接口:GET /scn/task-instances/{id}/proofs、GET /scn/task-proofs/{id};
  DELETE /scn/task-proofs/{id} 软删(deleted_at 置位,列表不再返回)。
- 旧客户端单值 proof_object_key 过渡仍可用;驳回重交时证据集合整体替换。
- DEV-42:复活+新增混合提交读取顺序恒等于本次提交顺序(proof_url 恒为
  keys[0]);DELETE 状态闸门(PENDING_REVIEW 及之后 409 拒删)。

需要可连接的数据库(远程优先),不可达时该模块内用例会被 `db_ready` fixture 跳过。
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.db.engine import AsyncSessionLocal
from app.dev.seed import SeededFamily
from app.models.enums import ProofKind, TaskStatus, UploadPurpose
from app.models.scn_task_proof import ScnTaskProof
from app.models.sys_upload import SysUpload
from app.services import auth_service

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


async def _proof_upload(
    db_session: AsyncSession,
    seeded_family: SeededFamily,
    *,
    label: str,
    content_type: str = "image/jpeg",
    uploader_account_id: str | None = None,
    size: int = 1,
) -> str:
    """造一条真实归属的 task_proof 台账行(测试不经过存储,直接写库)。"""
    key = f"proofs/{seeded_family.child_account.id}/{uuid4().hex}-{label}"
    db_session.add(SysUpload(
        family_id=seeded_family.family.id,
        uploader_account_id=uploader_account_id or seeded_family.child_account.id,
        storage_provider="local",
        object_key=key,
        bucket="local",
        public_url=f"/api/v1/files/{key}",
        content_type=content_type,
        size=size,
        purpose=UploadPurpose.TASK_PROOF,
    ))
    await db_session.commit()
    return key


async def _started_task(
    api_client: AsyncClient, seeded_family: SeededFamily, db_session: AsyncSession
) -> tuple[dict, dict[str, str], dict[str, str]]:
    """家长建任务 + 孩子接取,返回 (task, parent_headers, child_headers)。"""
    parent_headers = _auth_headers(seeded_family.parent)
    child_headers = _auth_headers(seeded_family.child_account)
    task = await _create_task(api_client, parent_headers, seeded_family)
    resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/start", headers=child_headers
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"], parent_headers, child_headers


async def test_submit_multiple_proofs_success(
    api_client: AsyncClient, seeded_family: SeededFamily, db_session: AsyncSession
) -> None:
    """多 key(2 图 + 1 视频)提交成功;读取返回全部证据;scn_task_proof 行与 sys_upload 一一对应。"""
    await _top_up(db_session, seeded_family)
    task, parent_headers, child_headers = await _started_task(api_client, seeded_family, db_session)

    keys = [
        await _proof_upload(db_session, seeded_family, label="a", content_type="image/jpeg"),
        await _proof_upload(db_session, seeded_family, label="b", content_type="image/png"),
        await _proof_upload(db_session, seeded_family, label="c", content_type="video/mp4"),
    ]
    resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/submit",
        json={"proof_object_keys": keys},
        headers=child_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["status"] == TaskStatus.PENDING_REVIEW.value

    # TaskRead.proofs 返回全部证据,kind 由 content_type 推导,proof_url = 首个(过渡)
    proofs = data["proofs"]
    assert [p["kind"] for p in proofs] == [ProofKind.IMAGE.value, ProofKind.IMAGE.value, ProofKind.VIDEO.value]
    assert all(p["url"] for p in proofs)
    assert data["proof_url"] == proofs[0]["url"]

    # GET /scn/task-instances/{id}/proofs 与 TaskRead.proofs 同口径
    list_resp = await api_client.get(
        f"/api/v1/scn/task-instances/{task['id']}/proofs", headers=parent_headers
    )
    assert list_resp.status_code == 200
    listed = list_resp.json()["data"]
    assert [p["kind"] for p in listed] == [p["kind"] for p in proofs]

    # scn_task_proof 行与 sys_upload 一一对应(object_key 互相咬合)
    proof_rows = list((await db_session.execute(
        select(ScnTaskProof).where(ScnTaskProof.task_instance_id == task["id"])
    )).scalars().all())
    assert len(proof_rows) == 3
    upload_keys = set((await db_session.execute(
        select(SysUpload.object_key).where(SysUpload.object_key.in_(keys))
    )).scalars().all())
    assert {r.object_key for r in proof_rows} == upload_keys
    assert all(r.deleted_at is None for r in proof_rows)
    assert all(r.uploaded_by == seeded_family.child_account.id for r in proof_rows)


async def test_submit_rejects_cross_user_key(
    api_client: AsyncClient, seeded_family: SeededFamily, db_session: AsyncSession
) -> None:
    """跨用户 key(家长上传的凭证)混在集合里 → 整单 422,不留半提交状态。"""
    await _top_up(db_session, seeded_family)
    task, _parent_headers, child_headers = await _started_task(api_client, seeded_family, db_session)

    own = await _proof_upload(db_session, seeded_family, label="own")
    foreign = await _proof_upload(
        db_session, seeded_family, label="foreign",
        uploader_account_id=seeded_family.parent.id,
    )
    resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/submit",
        json={"proof_object_keys": [own, foreign]},
        headers=child_headers,
    )
    assert resp.status_code == 422, resp.text

    # 整单拒绝:任务留在 IN_PROGRESS,一条证据行都没落
    detail = await api_client.get(
        f"/api/v1/scn/task-instances/{task['id']}", headers=child_headers
    )
    assert detail.json()["data"]["status"] == TaskStatus.IN_PROGRESS.value
    rows = list((await db_session.execute(
        select(ScnTaskProof).where(ScnTaskProof.task_instance_id == task["id"])
    )).scalars().all())
    assert rows == []


async def test_submit_rejects_too_many_keys(
    api_client: AsyncClient, seeded_family: SeededFamily, db_session: AsyncSession
) -> None:
    """超过 max_proof_files(默认 9)拒绝;恰好等于上限允许。"""
    from app.config import settings

    await _top_up(db_session, seeded_family)
    task, _parent_headers, child_headers = await _started_task(api_client, seeded_family, db_session)

    limit = settings.upload.max_proof_files
    too_many = [await _proof_upload(db_session, seeded_family, label=f"n{i}") for i in range(limit + 1)]
    resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/submit",
        json={"proof_object_keys": too_many},
        headers=child_headers,
    )
    assert resp.status_code == 422, resp.text

    # 恰好等于上限:通过(用一个新任务,上一个任务没有状态变化,可继续用)
    resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/submit",
        json={"proof_object_keys": too_many[:limit]},
        headers=child_headers,
    )
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["data"]["proofs"]) == limit


async def test_submit_rejects_key_bound_to_other_task(
    api_client: AsyncClient, seeded_family: SeededFamily, db_session: AsyncSession
) -> None:
    """已提交到任务 A 的 key 不能再提交到任务 B(无论从台账还是证据表占用)。"""
    await _top_up(db_session, seeded_family)
    task_a, parent_headers, child_headers = await _started_task(api_client, seeded_family, db_session)
    key_a = await _proof_upload(db_session, seeded_family, label="a")
    resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task_a['id']}/submit",
        json={"proof_object_keys": [key_a]},
        headers=child_headers,
    )
    assert resp.status_code == 200, resp.text

    task_b = await _create_task(api_client, parent_headers, seeded_family)
    resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task_b['id']}/start", headers=child_headers
    )
    assert resp.status_code == 200, resp.text

    new_key = await _proof_upload(db_session, seeded_family, label="b")
    resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task_b['id']}/submit",
        json={"proof_object_keys": [new_key, key_a]},  # key_a 已被任务 A 占用
        headers=child_headers,
    )
    assert resp.status_code == 422, resp.text
    assert "占用" in resp.json()["msg"] or "关联其他任务" in resp.json()["msg"]


async def test_proof_read_and_soft_delete(
    api_client: AsyncClient, seeded_family: SeededFamily, db_session: AsyncSession
) -> None:
    """GET /scn/task-proofs/{id} 读取单条;DELETE 软删(deleted_at 置位,列表退出)。

    状态闸门(DEV-42):PENDING_REVIEW 期间拒删(409),驳回回到 IN_PROGRESS
    后恢复可删。
    """
    await _top_up(db_session, seeded_family)
    task, parent_headers, child_headers = await _started_task(api_client, seeded_family, db_session)

    keys = [
        await _proof_upload(db_session, seeded_family, label="keep", content_type="image/jpeg"),
        await _proof_upload(db_session, seeded_family, label="drop", content_type="video/mp4"),
    ]
    resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/submit",
        json={"proof_object_keys": keys},
        headers=child_headers,
    )
    assert resp.status_code == 200, resp.text
    proofs = resp.json()["data"]["proofs"]
    kept, dropped = proofs[0], proofs[1]

    # 单条读取
    get_resp = await api_client.get(
        f"/api/v1/scn/task-proofs/{dropped['id']}", headers=parent_headers
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["data"]["id"] == dropped["id"]

    # PENDING_REVIEW 期间禁删(DEV-42):上传者本人(孩子)与父母都被 409 拒绝
    child_del = await api_client.delete(
        f"/api/v1/scn/task-proofs/{dropped['id']}", headers=child_headers
    )
    assert child_del.status_code == 409, child_del.text
    parent_del = await api_client.delete(
        f"/api/v1/scn/task-proofs/{dropped['id']}", headers=parent_headers
    )
    assert parent_del.status_code == 409, parent_del.text
    row = await db_session.get(ScnTaskProof, dropped["id"])
    assert row is not None and row.deleted_at is None  # 未被软删

    # 驳回回到 IN_PROGRESS:删除重新开放,家长(非上传者)软删第二条
    reject_resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/reject",
        json={"comment": "第二张重拍"},
        headers=parent_headers,
    )
    assert reject_resp.status_code == 200, reject_resp.text
    del_resp = await api_client.delete(
        f"/api/v1/scn/task-proofs/{dropped['id']}", headers=parent_headers
    )
    assert del_resp.status_code == 200, del_resp.text

    # 上面 409 探测时已把行载入本会话 identity map,用新会话重读确认 API 侧软删落库
    async with AsyncSessionLocal() as fresh:
        row = await fresh.get(ScnTaskProof, dropped["id"])
    assert row is not None and row.deleted_at is not None  # 软删:行还在

    # 列表只剩第一条;软删的单条读取 404
    list_resp = await api_client.get(
        f"/api/v1/scn/task-instances/{task['id']}/proofs", headers=parent_headers
    )
    assert [p["id"] for p in list_resp.json()["data"]] == [kept["id"]]
    get_deleted = await api_client.get(
        f"/api/v1/scn/task-proofs/{dropped['id']}", headers=parent_headers
    )
    assert get_deleted.status_code == 404

    # 跨家庭不能读/删
    from app.dev.seed import cleanup_family, seed_basic_family

    other = await seed_basic_family(db_session, suffix="proof-other")
    try:
        other_parent_headers = _auth_headers(other.parent)
        cross_get = await api_client.get(
            f"/api/v1/scn/task-proofs/{kept['id']}", headers=other_parent_headers
        )
        assert cross_get.status_code == 403
        cross_del = await api_client.delete(
            f"/api/v1/scn/task-proofs/{kept['id']}", headers=other_parent_headers
        )
        assert cross_del.status_code == 403
    finally:
        await cleanup_family(db_session, other.family.id)


async def test_legacy_single_field_submit_still_works(
    api_client: AsyncClient, seeded_family: SeededFamily, db_session: AsyncSession
) -> None:
    """过渡:旧客户端 proof_object_key 单值提交 → 单元素集合,创建 1 条证据行。"""
    await _top_up(db_session, seeded_family)
    task, _parent_headers, child_headers = await _started_task(api_client, seeded_family, db_session)

    key = await _proof_upload(db_session, seeded_family, label="legacy")
    resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/submit",
        json={"proof_object_key": key},
        headers=child_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["status"] == TaskStatus.PENDING_REVIEW.value
    assert len(data["proofs"]) == 1
    assert data["proof_url"] == data["proofs"][0]["url"]

    rows = list((await db_session.execute(
        select(ScnTaskProof).where(ScnTaskProof.task_instance_id == task["id"])
    )).scalars().all())
    assert len(rows) == 1 and rows[0].object_key == key


async def test_resubmit_replaces_proof_set(
    api_client: AsyncClient, seeded_family: SeededFamily, db_session: AsyncSession
) -> None:
    """驳回重交:提交即"当前所选集合" —— 旧集合中未再携带的证据软删,新 key 建行。"""
    await _top_up(db_session, seeded_family)
    task, parent_headers, child_headers = await _started_task(api_client, seeded_family, db_session)

    keys_v1 = [
        await _proof_upload(db_session, seeded_family, label="v1a"),
        await _proof_upload(db_session, seeded_family, label="v1b"),
    ]
    resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/submit",
        json={"proof_object_keys": keys_v1},
        headers=child_headers,
    )
    assert resp.status_code == 200, resp.text

    reject_resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/reject",
        json={"comment": "第二张重拍"},
        headers=parent_headers,
    )
    assert reject_resp.status_code == 200, reject_resp.text

    # 重交:v1a 保留,v1b 换成新图 v2
    key_v2 = await _proof_upload(db_session, seeded_family, label="v2")
    resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/submit",
        json={"proof_object_keys": [keys_v1[0], key_v2]},
        headers=child_headers,
    )
    assert resp.status_code == 200, resp.text
    proofs = resp.json()["data"]["proofs"]
    assert len(proofs) == 2

    rows = list((await db_session.execute(
        select(ScnTaskProof).where(ScnTaskProof.task_instance_id == task["id"])
    )).scalars().all())
    by_key = {r.object_key: r for r in rows}
    assert by_key[keys_v1[0]].deleted_at is None   # 保留
    assert by_key[keys_v1[1]].deleted_at is not None  # 未再携带 → 软删
    assert by_key[key_v2].deleted_at is None       # 新增


async def test_submit_rejects_duplicate_and_empty(
    api_client: AsyncClient, seeded_family: SeededFamily, db_session: AsyncSession
) -> None:
    """重复 key / 空 key 列表拒绝(422)。"""
    await _top_up(db_session, seeded_family)
    task, _parent_headers, child_headers = await _started_task(api_client, seeded_family, db_session)

    key = await _proof_upload(db_session, seeded_family, label="dup")
    dup_resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/submit",
        json={"proof_object_keys": [key, key]},
        headers=child_headers,
    )
    assert dup_resp.status_code == 422, dup_resp.text

    empty_resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/submit",
        json={"proof_object_keys": []},
        headers=child_headers,
    )
    assert empty_resp.status_code == 422, empty_resp.text


async def test_mixed_revive_submit_order_follows_keys(
    api_client: AsyncClient, seeded_family: SeededFamily, db_session: AsyncSession
) -> None:
    """复活+新增混合提交(DEV-42):读取顺序恒等于本次提交顺序。

    回归:复活行若保留上次提交的 created_at,会排在本次新建行之前,
    proofs[0](= proof_url)就不再是 keys[0](= task.proof_object_key)。
    修法:复活时 created_at 一并按本次提交序位重排。
    """
    await _top_up(db_session, seeded_family)
    task, parent_headers, child_headers = await _started_task(api_client, seeded_family, db_session)

    keys_v1 = [
        await _proof_upload(db_session, seeded_family, label="v1a"),
        await _proof_upload(db_session, seeded_family, label="v1b"),
    ]
    resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/submit",
        json={"proof_object_keys": keys_v1},
        headers=child_headers,
    )
    assert resp.status_code == 200, resp.text

    reject_resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/reject",
        json={"comment": "重拍"},
        headers=parent_headers,
    )
    assert reject_resp.status_code == 200, reject_resp.text

    # 混合提交:新建 k3 排第 1,复活 v1a 排第 2 —— 若复活行保留旧 created_at,
    # v1a 会凭旧时间戳排到 k3 前面,proof_url 与 keys[0] 错位。
    key_v2 = await _proof_upload(db_session, seeded_family, label="v2")
    resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/submit",
        json={"proof_object_keys": [key_v2, keys_v1[0]]},
        headers=child_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    proofs = data["proofs"]

    # 按 id 反查 object_key:API 顺序 == 本次提交顺序 [v2, v1a]
    rows = {r.id: r for r in (await db_session.execute(
        select(ScnTaskProof).where(ScnTaskProof.task_instance_id == task["id"])
    )).scalars().all()}
    assert [rows[p["id"]].object_key for p in proofs] == [key_v2, keys_v1[0]]
    assert data["proof_url"] == proofs[0]["url"]

    # 读取口径(ORDER BY created_at, id)与提交顺序一致;v1b 保持软删
    ordered = list((await db_session.execute(
        select(ScnTaskProof)
        .where(ScnTaskProof.task_instance_id == task["id"])
        .order_by(ScnTaskProof.created_at, ScnTaskProof.id)
    )).scalars().all())
    assert [r.object_key for r in ordered if r.deleted_at is None] == [key_v2, keys_v1[0]]
    assert next(r for r in ordered if r.object_key == keys_v1[1]).deleted_at is not None


async def test_delete_proof_blocked_in_completed(
    api_client: AsyncClient, seeded_family: SeededFamily, db_session: AsyncSession
) -> None:
    """审核通过(COMPLETED)后同样禁删(409)—— PENDING_REVIEW 及之后一律拒删。"""
    await _top_up(db_session, seeded_family)
    task, parent_headers, child_headers = await _started_task(api_client, seeded_family, db_session)

    key = await _proof_upload(db_session, seeded_family, label="done")
    resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/submit",
        json={"proof_object_keys": [key]},
        headers=child_headers,
    )
    assert resp.status_code == 200, resp.text
    proof_id = resp.json()["data"]["proofs"][0]["id"]

    approve_resp = await api_client.post(
        f"/api/v1/scn/task-instances/{task['id']}/approve",
        json={"rating": 5},
        headers=parent_headers,
    )
    assert approve_resp.status_code == 200, approve_resp.text

    del_resp = await api_client.delete(
        f"/api/v1/scn/task-proofs/{proof_id}", headers=parent_headers
    )
    assert del_resp.status_code == 409, del_resp.text
    row = await db_session.get(ScnTaskProof, proof_id)
    assert row is not None and row.deleted_at is None


async def test_task_proof_upload_enforces_content_type_and_size(
    api_client: AsyncClient, seeded_family: SeededFamily, monkeypatch
) -> None:
    """上传口收口(UploadSection):task_proof 的类型白名单 / 大小上限,422 而非落库。"""
    from app.common.storage import get_storage
    from app.config import settings as app_settings

    child_headers = _auth_headers(seeded_family.child_account)
    get_storage.cache_clear()
    monkeypatch.setattr(app_settings.storage, "provider", "local")
    try:
        # 类型不在白名单(application/pdf)
        resp = await api_client.post(
            "/api/v1/sys/uploads",
            headers=child_headers,
            data={"purpose": UploadPurpose.TASK_PROOF.value},
            files={"file": ("doc.pdf", b"x", "application/pdf")},
        )
        assert resp.status_code == 422, resp.text

        # 超过大小上限(把上限压到 0MB,任意内容即超)
        monkeypatch.setattr(app_settings.upload, "max_proof_file_mb", 0)
        resp = await api_client.post(
            "/api/v1/sys/uploads",
            headers=child_headers,
            data={"purpose": UploadPurpose.TASK_PROOF.value},
            files={"file": ("proof.jpg", b"fake-image-bytes", "image/jpeg")},
        )
        assert resp.status_code == 422, resp.text
    finally:
        get_storage.cache_clear()
