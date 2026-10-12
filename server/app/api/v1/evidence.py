"""证据清理路由(docs/07 A7.3,DEV-44)。

- `POST /scn/evidence/purge-preview`:统计将清理的证据/文件,不执行删除;
- `POST /scn/evidence/purge`:软删到期证据;`hard_delete=true` 时立即物理删除。

权限口径(管理端/队长):仅 GUILD_MASTER(父母/会长)可调用,且只能清理
本家庭(family_id 取当前登录账号)的证据 —— 本仓库未单独建管理后台角色,
Admin 侧后续如需跨家庭清理,走定时任务或另开管理端接口。

真正的定时真删(软删保留 180 天后)由调度器 `purge_expired_evidence`
每日执行,不经过这两个接口(见 app/workers/scheduler.py)。
"""
from __future__ import annotations

from fastapi import APIRouter

from app.deps import DBSession, GuildMasterOnly
from app.schemas.common import ApiResponse, ok
from app.schemas.evidence import (
    EvidencePurgePreviewRequest,
    EvidencePurgePreviewResponse,
    EvidencePurgeRequest,
    EvidencePurgeResponse,
)
from app.services import evidence_cleanup_service

router = APIRouter(prefix="/scn/evidence", tags=["scn-evidence"])


@router.post(
    "/purge-preview",
    response_model=ApiResponse[EvidencePurgePreviewResponse],
    summary="清理预览:统计将清理的证据/文件(数量、占用空间),不执行删除",
)
async def purge_preview(
    body: EvidencePurgePreviewRequest, db: DBSession, user: GuildMasterOnly,
) -> ApiResponse[EvidencePurgePreviewResponse]:
    preview = await evidence_cleanup_service.preview_purge(
        db, family_id=user.family_id,
        older_than_days=body.older_than_days, proof_ids=body.proof_ids,
    )
    return ok(preview)


@router.post(
    "/purge",
    response_model=ApiResponse[EvidencePurgeResponse],
    summary="执行清理:软删到期证据(hard_delete=true 时立即物理删除)",
)
async def purge(
    body: EvidencePurgeRequest, db: DBSession, user: GuildMasterOnly,
) -> ApiResponse[EvidencePurgeResponse]:
    result = await evidence_cleanup_service.purge(
        db, family_id=user.family_id,
        older_than_days=body.older_than_days, proof_ids=body.proof_ids,
        hard_delete=body.hard_delete,
    )
    return ok(result)
