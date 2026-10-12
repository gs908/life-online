"""证据清理 DTO(docs/07 A7.3,DEV-44)。

`POST /scn/evidence/purge-preview` 统计将清理的证据/台账文件,不执行删除;
`POST /scn/evidence/purge` 按同一口径软删(hard_delete=false,默认)或
立即物理删除(hard_delete=true)。定时真删(软删保留 180 天后)走调度器,
不经过这两个接口。
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import ProofKind


class EvidencePurgePreviewRequest(BaseModel):
    """清理候选的筛选口径。留空时按配置的默认账龄(purge_default_days)。"""

    older_than_days: int | None = Field(default=None, ge=1, le=3650)
    proof_ids: list[str] | None = Field(
        default=None,
        description="显式选择证据 id(优先于账龄过滤,仍限本家庭、仅未软删行)",
    )


class EvidencePurgeRequest(EvidencePurgePreviewRequest):
    """purge 执行口径。hard_delete=true 时立即物理删除(对象 + 台账行 + 证据行)。"""

    hard_delete: bool = False


class EvidencePurgeItem(BaseModel):
    """一条将清理的证据(预览 items / 执行结果明细共用)。"""

    proof_id: str
    task_instance_id: str
    object_key: str
    kind: ProofKind
    size: int
    content_type: str
    created_at: datetime


class EvidencePurgePreviewResponse(BaseModel):
    """预览统计(docs/06 §6.3 口径:count + 占用空间 + items)。"""

    older_than_days: int
    evidence_count: int
    upload_count: int  # 将连带软删/真删的 sys_upload 台账行数
    total_size: int  # 字节
    total_size_mb: float
    items: list[EvidencePurgeItem]  # 最多截断 200 条,数量以 evidence_count 为准


class EvidencePurgeResponse(BaseModel):
    """执行结果摘要。mode=soft 时 objects 恒为 0(软删不动对象)。"""

    mode: str  # "soft" | "hard"
    proofs: int  # 软删/删除的证据行数
    uploads: int  # 软删/删除的台账行数
    objects: int  # 物理删除的对象存储文件数(软删为 0)
    failed_objects: int  # 对象删除失败数(hard 时重试可直接再跑,幂等)
    items: list[EvidencePurgeItem]  # 本次实际处理的证据
