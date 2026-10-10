"""上传服务:把文件存到对象存储并写 SysUpload 元数据。

对象存储路径规范(DEV-20,产品评论约定):
    `{prefix}/{用户}/{年}/{月}/{日}/{任务号}-{文件序号}.{扩展名}`
- prefix / bucket 由 yaml(`storage.minio.prefix` / `storage.local.prefix` 等)统一管理,
  bucket 由存储实现自持,完整定位 = bucket + key;
- 用户 = 上传者账号 id;年/月/日按北京时区自然日切分;
- 任务号 = 关联任务实例 id(`task_id` 表单字段);非任务上传(头像/横幅等)以 purpose 代替;
- 文件序号 = 同一 用户+日期+任务号 维度下的自增序号(按已有 key 前缀计数)。
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.storage import ObjectInfo, StorageClient, get_storage
from app.common.timeutil import now_bj
from app.models.enums import UploadPurpose
from app.models.sys_account import SysAccount
from app.models.sys_upload import SysUpload

# 常见 content-type -> 扩展名兜底(文件名无后缀时使用)
_CONTENT_TYPE_EXT = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/gif": "gif",
    "image/webp": "webp",
    "video/mp4": "mp4",
    "video/quicktime": "mov",
    "application/pdf": "pdf",
}


def _file_ext(filename: str, content_type: str) -> str:
    name = (filename or "").rsplit("/", 1)[-1]
    if "." in name:
        ext = name.rsplit(".", 1)[1].lower()
        # 只保留字母数字,防止扩展名里夹路径/特殊字符
        ext = "".join(ch for ch in ext if ch.isalnum())
        if ext:
            return ext[:8]
    return _CONTENT_TYPE_EXT.get((content_type or "").split(";")[0].strip().lower(), "bin")


def _key_head(storage: StorageClient, *, user_id: str, task_no: str) -> str:
    """序号计数用的 key 前缀(不含序号与扩展名)。日期取北京时区当天。"""
    today = now_bj()
    relative = f"{user_id}/{today.year:04d}/{today.month:02d}/{today.day:02d}/{task_no}-"
    return storage.full_key(relative)


async def _next_seq(db: AsyncSession, key_head: str) -> int:
    """同前缀已有上传数 + 1 作为下一个文件序号。"""
    stmt = select(func.count()).select_from(SysUpload).where(
        SysUpload.object_key.like(f"{key_head}%")
    )
    count = (await db.execute(stmt)).scalar_one()
    return int(count) + 1


async def save_upload(
    db: AsyncSession, *,
    family_id: str,
    uploader: SysAccount,
    content: bytes,
    content_type: str,
    purpose: UploadPurpose,
    filename: str,
    task_id: str | None = None,
) -> SysUpload:
    storage = get_storage()

    # 任务证明类上传若带 task_id,先校验任务存在且属于本家庭,杜绝跨家庭引用/伪造路径段
    task_no = purpose.value
    if task_id:
        from app.common.exceptions import NotFoundError
        from app.models.scn_task_instance import ScnTaskInstance
        task = await db.get(ScnTaskInstance, task_id)
        if task is None or task.family_id != family_id:
            raise NotFoundError(f"任务 {task_id} 不存在")
        task_no = task_id

    await storage.ensure_bucket()

    ext = _file_ext(filename, content_type)
    key_head = _key_head(storage, user_id=uploader.id, task_no=task_no)
    seq = await _next_seq(db, key_head)
    key = f"{key_head}{seq}.{ext}"
    # 并发上传撞序号时(object_key 唯一索引)顺延取号
    while (await db.execute(select(SysUpload.id).where(SysUpload.object_key == key))).first():
        seq += 1
        key = f"{key_head}{seq}.{ext}"

    info: ObjectInfo = await storage.upload(key, content, content_type=content_type)
    access_url = storage.presign_get(info.key)

    record = SysUpload(
        family_id=family_id,
        uploader_account_id=uploader.id,
        storage_provider=storage.provider_name,
        object_key=info.key,
        bucket=info.bucket,
        # MinIO 预签名 URL 会过期,不落库;读取时按 object_key 现算(access_url 字段)。
        # local 模式 URL 稳定,落库即最终 URL。
        public_url=access_url if storage.provider_name == "local" else None,
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
