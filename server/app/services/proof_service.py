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

from app.common.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from app.common.timeutil import utcnow
from app.models.enums import ProofKind, TaskStatus, UserRole
from app.models.scn_task_instance import ScnTaskInstance
from app.models.scn_task_proof import ScnTaskProof
from app.models.sys_account import SysAccount


def _enum_value(value) -> str:
    return value.value if hasattr(value, "value") else str(value)

# 进入审核后(PENDING_REVIEW 及之后)禁止删除证据:审核中的证据集合是审核
# 依据,删光/删改会让审核失去对象(DEV-42,默认口径)。驳回会回到
# IN_PROGRESS,重新开放删除;AVAILABLE/IN_PROGRESS 维持原口径可删。
DELETE_BLOCKED_STATUSES = frozenset({
    TaskStatus.PENDING_REVIEW,
    TaskStatus.COMPLETED,
    TaskStatus.EXPIRED,
})


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

    状态闸门(DEV-42):任务进入审核(PENDING_REVIEW 及之后)后禁止删除,
    409 —— 审核中的证据集合是审核依据,不允许在审核期间被删改;驳回回到
    IN_PROGRESS 后重新开放。权限:本家庭成员,且是证据上传者本人或父母
    (GUILD_MASTER)—— 未提交/被打回时,家长可替孩子撤下不合适的图,
    孩子也可在重新提交前自行调整。
    """
    if proof.family_id != actor.family_id:
        raise PermissionDeniedError("只能操作自己家庭任务证据")
    actor_role = actor.role.value if hasattr(actor.role, "value") else str(actor.role)
    if proof.uploaded_by != actor.id and actor_role != UserRole.GUILD_MASTER.value:
        raise PermissionDeniedError("只有证据上传者或父母可以删除该证据")
    task = await db.get(ScnTaskInstance, proof.task_instance_id)
    if task is not None and task.status in DELETE_BLOCKED_STATUSES:
        raise ConflictError(
            f"任务已进入审核({_enum_value(task.status)}),证据不可删除"
        )
    proof.deleted_at = utcnow()
    await db.commit()
    await db.refresh(proof)
    return proof
