"""上传路由:前端 multipart/form-data 上传文件,后端写入当前配置的存储后端并记录元数据。"""
from __future__ import annotations

from fastapi import APIRouter, File, Form, UploadFile

from app.deps import CurrentUser, DBSession
from app.models.enums import UploadPurpose
from app.schemas.common import ApiResponse, ok
from app.schemas.upload import UploadRead
from app.services import upload_service

router = APIRouter(prefix="/sys/uploads", tags=["sys-uploads"])

# public_url 只对本地文件存储可信(local 的 URL 是稳定路径)。
# 存量回归(Mars 审查 🟡):旧实现曾把 MinIO 预签名 URL 落库,该类 URL 带签名会过期,
# 读取端若继续信任存量 minio 行的 public_url 会一直返回失效链接 —— 因此 minio 行
# 一律忽略 public_url、按 object_key 现算 access_url。选读取端忽略而非一次性迁移:
# 无需对每个跑过 minio 的环境执行 UPDATE,部署即生效,且对 local 行为零影响;
# minio 行的存量 public_url 已成死数据,可留待任意维护窗口清理。
_LOCAL_PROVIDERS = {"local", "filestorage", "file"}


def _effective_public_url(u) -> str | None:
    if u.storage_provider in _LOCAL_PROVIDERS:
        return u.public_url
    return None


def _to_read(u) -> UploadRead:
    public_url = _effective_public_url(u)
    return UploadRead(
        id=u.id,
        family_id=u.family_id,
        uploader_account_id=u.uploader_account_id,
        storage_provider=u.storage_provider,
        object_key=u.object_key,
        bucket=u.bucket,
        public_url=public_url,
        content_type=u.content_type,
        size=u.size,
        purpose=u.purpose,
        access_url=public_url or upload_service.build_access_url(u.object_key),
        created_at=u.created_at,
    )


@router.post("", response_model=ApiResponse[UploadRead], summary="上传文件")
async def upload(
    db: DBSession, user: CurrentUser,
    file: UploadFile = File(...),
    purpose: UploadPurpose = Form(default=UploadPurpose.OTHER),
    task_id: str | None = Form(default=None),
) -> ApiResponse[UploadRead]:
    """multipart 上传:file + purpose + 可选 task_id。

    task_id(purpose=task_proof 时建议携带)用于对象存储路径规范中的"任务号"段:
    `{prefix}/{用户}/{年}/{月}/{日}/{任务号}-{文件序号}.{扩展名}`。
    """
    content = await file.read()
    fname = file.filename or "upload.bin"
    record = await upload_service.save_upload(
        db, family_id=user.family_id, uploader=user,
        content=content, content_type=file.content_type or "application/octet-stream",
        purpose=purpose, filename=fname, task_id=task_id,
    )
    return ok(_to_read(record))
