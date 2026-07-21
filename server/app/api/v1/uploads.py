"""上传路由:前端 multipart/form-data 上传文件,后端写入当前配置的存储后端并记录元数据。"""
from __future__ import annotations

from fastapi import APIRouter, File, Form, UploadFile

from app.deps import CurrentUser, DBSession
from app.models.enums import UploadPurpose
from app.schemas.common import ApiResponse, ok
from app.schemas.upload import UploadRead
from app.services import upload_service

router = APIRouter(prefix="/sys/uploads", tags=["sys-uploads"])


def _to_read(u) -> UploadRead:
    return UploadRead(
        id=u.id,
        family_id=u.family_id,
        uploader_account_id=u.uploader_account_id,
        storage_provider=u.storage_provider,
        object_key=u.object_key,
        bucket=u.bucket,
        public_url=u.public_url,
        content_type=u.content_type,
        size=u.size,
        purpose=u.purpose,
        access_url=u.public_url or upload_service.build_access_url(u.object_key),
        created_at=u.created_at,
    )


@router.post("", response_model=ApiResponse[UploadRead], summary="上传文件")
async def upload(
    db: DBSession, user: CurrentUser,
    file: UploadFile = File(...),
    purpose: UploadPurpose = Form(default=UploadPurpose.OTHER),
) -> ApiResponse[UploadRead]:
    content = await file.read()
    fname = file.filename or "upload.bin"
    record = await upload_service.save_upload(
        db, family_id=user.family_id, uploader=user,
        content=content, content_type=file.content_type or "application/octet-stream",
        purpose=purpose, filename=fname,
    )
    return ok(_to_read(record))
