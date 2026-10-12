"""证据清理测试(docs/07 A7.3,DEV-44)。

覆盖:
- purge-preview 统计口径:只含本家庭、未软删、账龄达标的证据;数量/占用空间正确,
  不执行删除;
- purge 软删:`scn_task_proof.deleted_at` + `sys_upload.deleted_at` 置位(行与对象
  保留);proof_ids 显式子集只清选中项;孩子(ADVENTURER)403;幂等(二次执行 0);
- purge 硬删(hard_delete=true):对象存储文件 + 台账行 + 证据行一并移除;
- 定时真删边界:软删 179 天保留、180 天(含)即删(`hard_delete_after_days` 边界),
  对象删除失败时行保留待重试。

需要可连接的数据库(远程优先),不可达时该模块内用例会被 `db_ready` fixture 跳过。
"""
from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.storage import get_storage
from app.common.timeutil import utcnow
from app.config import settings as app_settings
from app.dev.seed import SeededFamily
from app.models.enums import ProofKind, UploadPurpose
from app.models.scn_task_proof import ScnTaskProof
from app.models.sys_upload import SysUpload
from app.services import auth_service, evidence_cleanup_service

pytestmark = pytest.mark.db

OLD_DAYS = app_settings.upload.purge_default_days  # 默认账龄口径(180)


def _auth_headers(account) -> dict[str, str]:
    tokens = auth_service.issue_token_pair(account)
    return {"Authorization": f"Bearer {tokens.access_token}"}


async def _seed_proof(
    db_session: AsyncSession,
    seeded_family: SeededFamily,
    *,
    label: str,
    created_days_ago: int = 0,
    size: int = 100,
    deleted_days_ago: int | None = None,
    family_id: str | None = None,
    with_file: bool = False,
) -> str:
    """直接造一对台账行 + 证据行(可回溯创建/软删时间,不走完整任务流)。"""
    key = f"proofs/{uuid4().hex}-{label}"
    db_session.add(SysUpload(
        family_id=family_id or seeded_family.family.id,
        uploader_account_id=seeded_family.child_account.id,
        storage_provider="local",
        object_key=key,
        bucket="local",
        public_url=f"/api/v1/files/{key}",
        content_type="image/jpeg",
        size=size,
        purpose=UploadPurpose.TASK_PROOF,
    ))
    await db_session.flush()

    proof = ScnTaskProof(
        family_id=family_id or seeded_family.family.id,
        task_instance_id=seeded_family.task_instance.id,
        kind=ProofKind.IMAGE,
        object_key=key,
        size=size,
        content_type="image/jpeg",
        uploaded_by=seeded_family.child_account.id,
        created_at=utcnow() - timedelta(days=created_days_ago),
    )
    if deleted_days_ago is not None:
        proof.deleted_at = utcnow() - timedelta(days=deleted_days_ago)
    db_session.add(proof)
    await db_session.commit()

    if with_file:
        # local 存储根目录下放一个真实文件,验证硬删确实删掉对象
        storage = get_storage()
        path = storage._path_for(storage.full_key(key))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fake-image")
    return key


@pytest.fixture
def local_storage(tmp_path, monkeypatch):
    """把存储切到 local + 临时根目录(硬删用例验证真实文件被删除)。"""
    get_storage.cache_clear()
    monkeypatch.setattr(app_settings.storage, "provider", "local")
    monkeypatch.setattr(app_settings.storage.local, "root_path", str(tmp_path))
    get_storage.cache_clear()
    yield get_storage()
    get_storage.cache_clear()


async def test_purge_preview_counts_only_eligible(
    db_session: AsyncSession, seeded_family: SeededFamily
) -> None:
    """预览只统计:本家庭 + 未软删 + 账龄达标;不执行删除。"""
    from app.dev.seed import cleanup_family, seed_basic_family

    old_a = await _seed_proof(db_session, seeded_family, label="old-a", created_days_ago=OLD_DAYS + 1, size=100)
    old_b = await _seed_proof(db_session, seeded_family, label="old-b", created_days_ago=OLD_DAYS + 30, size=200)
    await _seed_proof(db_session, seeded_family, label="young", created_days_ago=0, size=999)
    await _seed_proof(db_session, seeded_family, label="already-deleted", created_days_ago=OLD_DAYS + 1, deleted_days_ago=1)
    other = await seed_basic_family(db_session, suffix="purge-preview")
    try:
        await _seed_proof(db_session, other, label="other-family", created_days_ago=OLD_DAYS + 1)

        preview = await evidence_cleanup_service.preview_purge(
            db_session, family_id=seeded_family.family.id
        )
    finally:
        await cleanup_family(db_session, other.family.id)
    assert preview.older_than_days == OLD_DAYS
    assert preview.evidence_count == 2
    assert preview.upload_count == 2
    assert preview.total_size == 300
    assert preview.total_size_mb == round(300 / (1024 * 1024), 2)
    assert {i.object_key for i in preview.items} == {old_a, old_b}

    # 预览是只读的:库内状态不变
    rows = list((await db_session.execute(
        select(ScnTaskProof).where(ScnTaskProof.object_key.in_([old_a, old_b]))
    )).scalars().all())
    assert all(r.deleted_at is None for r in rows)

    # 显式 older_than_days 覆盖默认口径
    preview_wide = await evidence_cleanup_service.preview_purge(
        db_session, family_id=seeded_family.family.id, older_than_days=1
    )
    assert preview_wide.evidence_count == 2  # young(created 0 天)仍不入选


async def test_purge_soft_delete_marks_proof_and_ledger(
    api_client: AsyncClient, db_session: AsyncSession, seeded_family: SeededFamily
) -> None:
    """软删:证据行 + 台账行 deleted_at 置位,行保留;孩子 403;二次执行幂等。"""
    old_key = await _seed_proof(db_session, seeded_family, label="old", created_days_ago=OLD_DAYS + 1, size=100)
    young_key = await _seed_proof(db_session, seeded_family, label="young", created_days_ago=0)

    # 孩子(ADVENTURER)无权调用 —— 管理端/队长口径
    child_headers = _auth_headers(seeded_family.child_account)
    resp = await api_client.post(
        "/api/v1/scn/evidence/purge-preview", json={}, headers=child_headers
    )
    assert resp.status_code == 403
    resp = await api_client.post("/api/v1/scn/evidence/purge", json={}, headers=child_headers)
    assert resp.status_code == 403

    parent_headers = _auth_headers(seeded_family.parent)
    resp = await api_client.post(
        "/api/v1/scn/evidence/purge", json={}, headers=parent_headers
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["mode"] == "soft"
    assert data["proofs"] == 1
    assert data["uploads"] == 1
    assert data["objects"] == 0

    proof = (await db_session.execute(
        select(ScnTaskProof).where(ScnTaskProof.object_key == old_key)
    )).scalar_one()
    assert proof.deleted_at is not None  # 软删:行保留
    upload = (await db_session.execute(
        select(SysUpload).where(SysUpload.object_key == old_key)
    )).scalar_one()
    assert upload.deleted_at is not None  # 台账行跟随软删
    # 未到期证据与台账不动
    young_proof = (await db_session.execute(
        select(ScnTaskProof).where(ScnTaskProof.object_key == young_key)
    )).scalar_one()
    assert young_proof.deleted_at is None

    # 预览归零;再执行一次幂等(0 条)
    resp = await api_client.post(
        "/api/v1/scn/evidence/purge-preview", json={}, headers=parent_headers
    )
    assert resp.json()["data"]["evidence_count"] == 0
    resp = await api_client.post("/api/v1/scn/evidence/purge", json={}, headers=parent_headers)
    assert resp.json()["data"]["proofs"] == 0


async def test_purge_respects_explicit_proof_ids(
    db_session: AsyncSession, seeded_family: SeededFamily
) -> None:
    """proof_ids 显式子集:只清选中项(仍限本家庭),账龄外的选中项也清。"""
    old_key = await _seed_proof(db_session, seeded_family, label="old", created_days_ago=OLD_DAYS + 1)
    fresh_key = await _seed_proof(db_session, seeded_family, label="fresh", created_days_ago=0)

    proof_fresh = (await db_session.execute(
        select(ScnTaskProof).where(ScnTaskProof.object_key == fresh_key)
    )).scalar_one()
    result = await evidence_cleanup_service.purge(
        db_session, family_id=seeded_family.family.id, proof_ids=[proof_fresh.id],
    )
    assert result.proofs == 1 and result.items[0].object_key == fresh_key

    by_key = {k: r for k, r in (await db_session.execute(
        select(ScnTaskProof.object_key, ScnTaskProof)
        .where(ScnTaskProof.object_key.in_([old_key, fresh_key]))
    )).all()}
    assert by_key[fresh_key].deleted_at is not None   # 显式选中,账龄外也清
    assert by_key[old_key].deleted_at is None         # 未选中不动

    # 跨家庭 proof_id 拒绝(他人家庭的 id 不生效)
    from app.dev.seed import cleanup_family, seed_basic_family

    other = await seed_basic_family(db_session, suffix="purge-ids")
    try:
        other_key = await _seed_proof(db_session, other, label="other", created_days_ago=0)
        other_proof = (await db_session.execute(
            select(ScnTaskProof).where(ScnTaskProof.object_key == other_key)
        )).scalar_one()
        result = await evidence_cleanup_service.purge(
            db_session, family_id=seeded_family.family.id, proof_ids=[other_proof.id],
        )
    finally:
        await cleanup_family(db_session, other.family.id)
    assert result.proofs == 0


async def test_purge_hard_delete_removes_object_and_rows(
    db_session: AsyncSession, seeded_family: SeededFamily, local_storage
) -> None:
    """hard_delete=true:对象存储文件 + 台账行 + 证据行一并移除。"""
    old_key = await _seed_proof(db_session, seeded_family, label="old", created_days_ago=OLD_DAYS + 1, with_file=True)

    result = await evidence_cleanup_service.purge(
        db_session, family_id=seeded_family.family.id, hard_delete=True,
    )
    assert result.mode == "hard"
    assert result.proofs == 1 and result.uploads == 1 and result.objects == 1

    assert (await db_session.execute(
        select(ScnTaskProof).where(ScnTaskProof.object_key == old_key)
    )).scalar_one_or_none() is None
    assert (await db_session.execute(
        select(SysUpload).where(SysUpload.object_key == old_key)
    )).scalar_one_or_none() is None
    # 对象存储文件确实没了
    storage = get_storage()
    assert not storage._path_for(storage.full_key(old_key)).exists()


async def test_hard_delete_expired_boundary(
    db_session: AsyncSession, seeded_family: SeededFamily, local_storage
) -> None:
    """定时真删边界:软删 179 天保留,180 天(含)即删;失败对象行保留待重试。"""
    keep = await _seed_proof(db_session, seeded_family, label="keep", deleted_days_ago=179, with_file=True)
    at_limit = await _seed_proof(db_session, seeded_family, label="at-limit", deleted_days_ago=180, with_file=True)
    beyond = await _seed_proof(db_session, seeded_family, label="beyond", deleted_days_ago=181, with_file=True)
    # 从未提交成证据的孤儿台账行(软删超期)也应被回收
    orphan_key = f"proofs/{uuid4().hex}-orphan"
    db_session.add(SysUpload(
        family_id=seeded_family.family.id,
        uploader_account_id=seeded_family.child_account.id,
        storage_provider="local",
        object_key=orphan_key,
        bucket="local",
        content_type="image/jpeg",
        size=1,
        purpose=UploadPurpose.TASK_PROOF,
        deleted_at=utcnow() - timedelta(days=181),
    ))
    await db_session.commit()

    stats = await evidence_cleanup_service.hard_delete_expired(db_session)
    assert stats["objects"] == 3  # at-limit + beyond + orphan
    assert stats["proofs"] == 2 and stats["uploads"] == 3

    rows = {r.object_key: r for r in (await db_session.execute(
        select(ScnTaskProof).where(ScnTaskProof.object_key.in_([keep, at_limit, beyond]))
    )).scalars().all()}
    assert rows[keep].deleted_at is not None      # 保留期内:行还在
    assert at_limit not in rows                    # 恰好 180 天:已物理删除(边界含)
    assert beyond not in rows

    uploads = {r.object_key: r for r in (await db_session.execute(
        select(SysUpload).where(SysUpload.object_key.in_([keep, at_limit, beyond, orphan_key]))
    )).scalars().all()}
    assert set(uploads) == {keep}                  # 其余台账行已物理删除
    assert uploads[keep].deleted_at is None        # 保留期内:台账行软删标记都不应有

    storage = get_storage()
    assert storage._path_for(storage.full_key(keep)).exists()
    assert not storage._path_for(storage.full_key(at_limit)).exists()
    assert not storage._path_for(storage.full_key(orphan_key)).exists()

    # 幂等:再跑一遍,只剩 keep 一条候选且不满足条件,计数为 0
    stats = await evidence_cleanup_service.hard_delete_expired(db_session)
    assert stats == {"proofs": 0, "uploads": 0, "objects": 0, "failed_objects": 0}


async def test_hard_delete_expired_keeps_rows_when_object_delete_fails(
    db_session: AsyncSession, seeded_family: SeededFamily, monkeypatch
) -> None:
    """对象删除失败:跳过行删除(先对象后行的顺序),计数进 failed_objects。"""
    from app.common.exceptions import StorageUnavailableError

    key = await _seed_proof(db_session, seeded_family, label="fail", deleted_days_ago=181)

    async def _boom(_key: str) -> None:
        raise StorageUnavailableError("minio down")

    monkeypatch.setattr(type(get_storage()), "delete", _boom)
    stats = await evidence_cleanup_service.hard_delete_expired(db_session)
    assert stats["failed_objects"] == 1
    assert stats["proofs"] == 0 and stats["uploads"] == 0

    proof = (await db_session.execute(
        select(ScnTaskProof).where(ScnTaskProof.object_key == key)
    )).scalar_one()
    assert proof.deleted_at is not None  # 行保留,等待下个周期重试
    assert (await db_session.execute(
        select(SysUpload).where(SysUpload.object_key == key)
    )).scalar_one() is not None
