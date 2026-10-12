"""任务证据服务(DEV-33 块 E):scn_task_proof 的读取与软删。

分层语义(见 docs/12 §5.2):
- `sys_upload` 是通用文件台账(上传即写,可多行,不感知任务状态);
- `scn_task_proof` 是任务证据,**提交时**按所选文件创建,`object_key` 逻辑引用
  `sys_upload.object_key`(无物理外键,台账真删不被证据表锁死)。

证据行的写入(提交时逐个创建/复活/收缩)在 task_service.submit_task 中,
本模块只负责读取与软删 —— 供 API 层与后续清理任务(A7.3)复用。
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exceptions import NotFoundError, PermissionDeniedError
from app.common.timeutil import utcnow
from app.models.enums import ProofKind, UserRole
from app.models.scn_task_proof import ScnTaskProof
from app.models.sys_account import SysAccount


def proof_kind_for_content_type(content_type: str) -> ProofKind | None:
    """按 content_type 推导证据 kind:image/*→IMAGE,video/*→VIDEO,audio/*→AUDIO。

    无法推导(如 application/pdf)返回 None,由调用方决定拒绝。
    """
    base = (content_type or "").split(";")[0].strip().lower()
    if base.startswith("image/"):
        return ProofKind.IMAGE
    if base.startswith("video/"):
        return ProofKind.VIDEO
    if base.startswith("audio/"):
        return ProofKind.AUDIO
    return None


async def list_proofs(
    db: AsyncSession, *, task_instance_id: str, include_deleted: bool = False,
) -> list[ScnTaskProof]:
    """任务的证据列表,按创建顺序返回;默认只含未软删的行。"""
    stmt = select(ScnTaskProof).where(ScnTaskProof.task_instance_id == task_instance_id)
    if not include_deleted:
        stmt = stmt.where(ScnTaskProof.deleted_at.is_(None))
    stmt = stmt.order_by(ScnTaskProof.created_at, ScnTaskProof.id)
    return list((await db.execute(stmt)).scalars().all())


async def get_proof(db: AsyncSession, proof_id: str) -> ScnTaskProof:
    proof = await db.get(ScnTaskProof, proof_id)
    if proof is None or proof.deleted_at is not None:
        raise NotFoundError(f"任务证据 {proof_id} 不存在")
    return proof


async def soft_delete_proof(
    db: AsyncSession, *, proof: ScnTaskProof, actor: SysAccount,
) -> ScnTaskProof:
    """软删一条证据(deleted_at 置位,行保留)。

    权限:本家庭成员,且是证据上传者本人或父母(GUILD_MASTER)——
    家长审核时可删不合适的图,孩子可在重新提交前自行撤下。
    """
    if proof.family_id != actor.family_id:
        raise PermissionDeniedError("只能操作自己家庭任务证据")
    actor_role = actor.role.value if hasattr(actor.role, "value") else str(actor.role)
    if proof.uploaded_by != actor.id and actor_role != UserRole.GUILD_MASTER.value:
        raise PermissionDeniedError("只有证据上传者或父母可以删除该证据")
    proof.deleted_at = utcnow()
    await db.commit()
    await db.refresh(proof)
    return proof
