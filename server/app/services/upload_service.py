"""上传服务:把文件存到对象存储并写 SysUpload 元数据。"""
from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.storage import ObjectInfo, get_storage
from app.config import settings
from app.models.enums import UploadPurpose
from app.models.sys_account import SysAccount
from app.models.sys_upload import SysUpload


def _build_object_key(purpose: UploadPurpose, family_id: str, filename: str) -> str:
    safe = filename.replace("/", "_").replace("\\", "_")
    suffix = uuid4().hex
    return f"{purpose.value}/{family_id}/{datetime.utcnow().strftime('%Y%m%d')}/{suffix}_{safe}"


async def save_upload(
    db: AsyncSession, *,
    family_id: str,
    uploader: SysAccount,
    content: bytes,
    content_type: str,
    purpose: UploadPurpose,
    filename: str,
) -> SysUpload:
    storage = get_storage()
    await storage.ensure_bucket()

    key = _build_object_key(purpose, family_id, filename)
    info: ObjectInfo = await storage.upload(key, content, content_type=content_type)
    access_url = storage.presign_get(info.key)

    record = SysUpload(
        family_id=family_id,
        uploader_account_id=uploader.id,
        storage_provider=settings.storage.provider,
        object_key=info.key,
        bucket=info.bucket,
        public_url=access_url,
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


async def get_upload(db: AsyncSession, upload_id: str) -> SysUpload:
    u = await db.get(SysUpload, upload_id)
    if not u:
        from app.common.exceptions import NotFoundError
        raise NotFoundError(f"上传 {upload_id} 不存在")
    return u


async def find_uploads(
    db: AsyncSession, *, family_id: str, purpose: UploadPurpose | None = None,
) -> list[SysUpload]:
    stmt = select(SysUpload).where(SysUpload.family_id == family_id)
    if purpose is not None:
        stmt = stmt.where(SysUpload.purpose == purpose)
    stmt = stmt.order_by(SysUpload.id.desc())
    return list((await db.execute(stmt)).scalars().all())
