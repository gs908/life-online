"""证据清理服务(docs/07 A7.3,DEV-44)。

三个入口,共用同一套候选口径:
- `preview_purge`:统计将清理的证据/文件(数量、占用空间),不执行删除;
- `purge`:软删到期证据(`scn_task_proof.deleted_at` / `sys_upload.deleted_at`
  置位,行与对象保留);`hard_delete=True` 时立即物理删除(对象 + 台账行 + 证据行),
  供父母显式确认后使用,默认不走;
- `hard_delete_expired`:定时真删 —— 软删后保留 `hard_delete_after_days`
  (默认 180 天,docs/05 §3.5"自动清理可配")的证据,物理删除对象存储文件
  与台账行,由调度器每日调用。

口径与不变量:
- 候选证据 = 本家庭未软删的 `scn_task_proof` 行,`created_at` 早于账龄截止
  (或 `proof_ids` 显式指定,仍限本家庭、仅未软删行);
- 台账行(`sys_upload`)跟随其证据:`scn_task_proof.object_key` 逻辑引用
  台账 `object_key`(无物理外键,docs/12 §5.2),证据被清理时台账行一并处置;
- **活跃引用保护**:仍有未软删证据引用的对象 key 一律不动 —— 软删时台账行
  保持活跃,真删时跳过(块 E 的提交复活路径 `submit_task` 可能复活证据行,
  该阀门保证复活后的证据永远取得到文件);
- 真删顺序 = 先删对象、后删行(与上传"先库后对象"互为镜像):对象删除失败
  跳过行删除,下个周期重试,不留"行没了、对象还在"的孤儿。
"""
from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exceptions import ValidationError
from app.common.storage import get_storage
from app.common.timeutil import utcnow
from app.config import settings
from app.models.scn_task_proof import ScnTaskProof
from app.models.sys_upload import SysUpload
from app.schemas.evidence import (
    EvidencePurgeItem,
    EvidencePurgePreviewResponse,
    EvidencePurgeResponse,
)

log = logging.getLogger(__name__)

# 预览/执行结果里 items 的截断上限(全量数量以 *_count 字段为准,避免响应爆炸)
_ITEMS_LIMIT = 200


def _to_item(p: ScnTaskProof) -> EvidencePurgeItem:
    return EvidencePurgeItem(
        proof_id=p.id,
        task_instance_id=p.task_instance_id,
        object_key=p.object_key,
        kind=p.kind,
        size=p.size,
        content_type=p.content_type,
        created_at=p.created_at,
    )


def _resolve_days(older_than_days: int | None) -> int:
    days = older_than_days or settings.upload.purge_default_days
    if days < 1:
        raise ValidationError("older_than_days 必须为正整数")
    return days


async def _select_candidates(
    db: AsyncSession, *, family_id: str,
    older_than_days: int, proof_ids: list[str] | None,
) -> list[ScnTaskProof]:
    """清理候选:本家庭未软删证据;proof_ids 显式指定时优先(仍限本家庭)。"""
    cutoff = utcnow() - timedelta(days=older_than_days)
    stmt = select(ScnTaskProof).where(
        ScnTaskProof.family_id == family_id,
        ScnTaskProof.deleted_at.is_(None),
    )
    if proof_ids is not None:
        if not proof_ids:
            raise ValidationError("proof_ids 为空列表请直接省略该参数,避免误清全部证据")
        stmt = stmt.where(ScnTaskProof.id.in_(proof_ids))
    else:
        stmt = stmt.where(ScnTaskProof.created_at < cutoff)
    stmt = stmt.order_by(ScnTaskProof.created_at, ScnTaskProof.id)
    return list((await db.execute(stmt)).scalars().all())


async def _active_object_keys(db: AsyncSession, object_keys: list[str]) -> set[str]:
    """候选 key 中仍被未软删证据引用的子集(活跃引用保护阀门)。"""
    if not object_keys:
        return set()
    rows = (await db.execute(
        select(ScnTaskProof.object_key).where(
            ScnTaskProof.object_key.in_(object_keys),
            ScnTaskProof.deleted_at.is_(None),
        )
    )).scalars().all()
    return set(rows)


async def preview_purge(
    db: AsyncSession, *, family_id: str,
    older_than_days: int | None = None, proof_ids: list[str] | None = None,
) -> EvidencePurgePreviewResponse:
    """统计将清理的证据与台账文件,不执行任何删除。"""
    days = _resolve_days(older_than_days)
    candidates = await _select_candidates(
        db, family_id=family_id, older_than_days=days, proof_ids=proof_ids
    )
    keys = [p.object_key for p in candidates]
    upload_count = 0
    if keys:
        upload_count = int((await db.execute(
            select(func.count()).select_from(SysUpload).where(SysUpload.object_key.in_(keys))
        )).scalar_one())
    total_size = sum(p.size for p in candidates)
    return EvidencePurgePreviewResponse(
        older_than_days=days,
        evidence_count=len(candidates),
        upload_count=upload_count,
        total_size=total_size,
        total_size_mb=round(total_size / (1024 * 1024), 2),
        items=[_to_item(p) for p in candidates[:_ITEMS_LIMIT]],
    )


async def purge(
    db: AsyncSession, *, family_id: str,
    older_than_days: int | None = None, proof_ids: list[str] | None = None,
    hard_delete: bool = False,
) -> EvidencePurgeResponse:
    """软删到期证据(hard_delete=False)或立即物理删除(True)。"""
    days = _resolve_days(older_than_days)
    candidates = await _select_candidates(
        db, family_id=family_id, older_than_days=days, proof_ids=proof_ids
    )
    keys = [p.object_key for p in candidates]
    if not candidates:
        return EvidencePurgeResponse(
            mode="hard" if hard_delete else "soft",
            proofs=0, uploads=0, objects=0, failed_objects=0, items=[],
        )

    if not hard_delete:
        now = utcnow()
        for p in candidates:
            p.deleted_at = now
        # 会话 autoflush=False:先显式落库软删标记,活跃引用阀门才能看到
        # "候选已不再活跃"(否则候选自己把自己挡住)。
        await db.flush()
        # 台账行跟随:仍被活跃证据引用的 key(理论上候选刚被软删,不应存在,
        # 阀门兜底并发/复活场景)保持不动。
        active_keys = await _active_object_keys(db, keys)
        uploads = list((await db.execute(
            select(SysUpload).where(SysUpload.object_key.in_(keys))
        )).scalars().all())
        ledger_hits = 0
        for u in uploads:
            if u.object_key in active_keys:
                continue
            u.deleted_at = now
            ledger_hits += 1
        await db.commit()
        return EvidencePurgeResponse(
            mode="soft", proofs=len(candidates), uploads=ledger_hits,
            objects=0, failed_objects=0,
            items=[_to_item(p) for p in candidates[:_ITEMS_LIMIT]],
        )

    # 物理删除:先删对象(失败跳过该条,行保留待重试),再删台账行与证据行
    storage = get_storage()
    failed_keys: set[str] = set()
    objects = 0
    for key in dict.fromkeys(keys):  # 去重保序,同一对象只删一次
        try:
            await storage.delete(key)
            objects += 1
        except Exception:
            log.exception("purge: 对象删除失败,本条跳过 key=%s", key)
            failed_keys.add(key)

    # 证据行随对象一起移除;对象没删成的行保留(软删状态不变),下个周期重试
    for p in candidates:
        if p.object_key not in failed_keys:
            await db.delete(p)
    # autoflush=False:显式落库删行,活跃引用阀门不再把候选自己算作活跃
    await db.flush()

    # 台账行:仍被活跃证据引用的 key 不动(候选删行后理论上为空,阀门兜底)
    ok_keys = [k for k in keys if k not in failed_keys]
    uploads = list((await db.execute(
        select(SysUpload).where(SysUpload.object_key.in_(ok_keys))
    )).scalars().all())
    active_keys = await _active_object_keys(db, ok_keys)
    ledger_hits = 0
    for u in uploads:
        if u.object_key in active_keys:
            continue
        await db.delete(u)
        ledger_hits += 1
    await db.commit()
    done = [p for p in candidates if p.object_key not in failed_keys]
    return EvidencePurgeResponse(
        mode="hard", proofs=len(done), uploads=ledger_hits,
        objects=objects, failed_objects=len(failed_keys),
        items=[_to_item(p) for p in done[:_ITEMS_LIMIT]],
    )


async def hard_delete_expired(db: AsyncSession, *, after_days: int | None = None) -> dict:
    """定时真删(调度器入口):物理删除软删超过保留期的证据/文件。

    跨家庭全量扫描;候选 =
    - `scn_task_proof.deleted_at <= 截止`(块 E 的 DELETE /scn/task-proofs/{id}
      只软删证据行,其台账行与对象在这里连带处置);
    - `sys_upload.deleted_at <= 截止` 的台账行(含从未提交成证据的孤儿上传)。
    返回计数供调度器日志。"""
    days = after_days if after_days is not None else settings.upload.hard_delete_after_days
    cutoff = utcnow() - timedelta(days=days)

    proof_rows = list((await db.execute(
        select(ScnTaskProof).where(
            ScnTaskProof.deleted_at.is_not(None),
            ScnTaskProof.deleted_at <= cutoff,
        )
    )).scalars().all())
    upload_rows = list((await db.execute(
        select(SysUpload).where(
            SysUpload.deleted_at.is_not(None),
            SysUpload.deleted_at <= cutoff,
        )
    )).scalars().all())

    # 台账候选并集:自身到期的行 + 被到期证据引用的行(证据已软删,文件随之退役)
    by_key = {u.object_key: u for u in upload_rows}
    for p in proof_rows:
        if p.object_key not in by_key:
            upload = await db.execute(
                select(SysUpload).where(SysUpload.object_key == p.object_key)
            )
            found = upload.scalar_one_or_none()
            if found is not None:
                by_key[p.object_key] = found

    # 活跃引用保护:仍被未软删证据引用的 key 一律不动
    candidate_keys = list(by_key)
    active_keys = await _active_object_keys(db, candidate_keys)

    storage = get_storage()
    objects = failed_objects = 0
    deletable_keys: list[str] = []
    for key in candidate_keys:
        if key in active_keys:
            continue
        try:
            await storage.delete(key)
            objects += 1
            deletable_keys.append(key)
        except Exception:
            log.exception("purge_expired: 对象删除失败,本条跳过 key=%s", key)
            failed_objects += 1

    deleted_uploads = 0
    for key in deletable_keys:
        await db.delete(by_key[key])
        deleted_uploads += 1
    deleted_proofs = 0
    for p in proof_rows:
        # 对象没删成(或仍被活跃证据引用)的证据行保留,留台账痕迹并等待重试
        if p.object_key in deletable_keys:
            await db.delete(p)
            deleted_proofs += 1
    await db.commit()

    stats = {
        "proofs": deleted_proofs,
        "uploads": deleted_uploads,
        "objects": objects,
        "failed_objects": failed_objects,
    }
    if any(stats.values()):
        log.info("purge_expired done, after_days=%s, %s", days, stats)
    return stats
