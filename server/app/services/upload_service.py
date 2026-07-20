"""上传服务:把文件存到对象存储并写 Upload 元数据。"""
from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.storage import ObjectInfo, get_storage
from app.models.enums import UploadPurpose
from app.models.upload import Upload
from app.models.user import User


def _build_object_key(purpose: UploadPurpose, family_id: str, filename: str) -> str:
    safe = filename.replace("/", "_").replace("\\", "_")
    suffix = uuid4().hex
    return f"{purpose.value}/{family_id}/{datetime.utcnow().strftime('%Y%m%d')}/{suffix}_{safe}"


async def save_upload(
    db: AsyncSession, *,
    family_id: str,
    uploader: User,
    content: bytes,
    content_type: str,
    purpose: UploadPurpose,
    filename: str,
) -> Upload:
    storage = get_storage()
    await storage.ensure_bucket()

    key = _build_object_key(purpose, family_id, filename)
    info: ObjectInfo = await storage.upload(key, content, content_type=content_type)

    record = Upload(
        family_id=family_id,
        uploader_id=uploader.id,
        object_key=info.key,
        bucket=info.bucket,
        content_type=content_type,
        size=info.size,
        purpose=purpose,
        etag=info.etag,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


def build_access_url(object_key: str, *, expires_seconds: int = 3600) -> str:
    storage = get_storage()
    return storage.presign_get(object_key, expires_seconds=expires_seconds)


async def get_upload(db: AsyncSession, upload_id: str) -> Upload:
    u = await db.get(Upload, upload_id)
    if not u:
        from app.common.exceptions import NotFoundError
        raise NotFoundError(f"上传 {upload_id} 不存在")
    return u


async def find_uploads(
    db: AsyncSession, *, family_id: str, purpose: UploadPurpose | None = None,
) -> list[Upload]:
    stmt = select(Upload).where(Upload.family_id == family_id)
    if purpose is not None:
        stmt = stmt.where(Upload.purpose == purpose)
    stmt = stmt.order_by(Upload.id.desc())
    return list((await db.execute(stmt)).scalars().all())
