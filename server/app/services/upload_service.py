"""上传服务:把文件存到对象存储并写 SysUpload 元数据。

对象存储路径规范(DEV-20,产品评论约定):
    `{prefix}/{用户}/{年}/{月}/{日}/{任务号}-{文件序号}.{扩展名}`
- prefix / bucket 由 yaml(`storage.minio.prefix` / `storage.local.prefix` 等)统一管理,
  bucket 由存储实现自持,完整定位 = bucket + key;
- 用户 = 上传者账号 id;年/月/日按北京时区自然日切分;
- 任务号 = 关联任务实例 id(`task_id` 表单字段);非任务上传(头像/横幅等)以 purpose 代替;
- 文件序号 = 同一 用户+日期+任务号 维度下的自增序号。

并发与孤儿闭环(Mars 审查 🟡):
- **先插库占位,后写对象** —— object_key 唯一索引在存储写入前仲裁并发:
  两个并发请求取到同一序号时,只有一个能 commit 占位成功,另一个撞
  IntegrityError 后重取号,杜绝"双方都先写对象、后者覆盖前者内容"的错乱;
- 占位成功后对象写入失败 → 删除占位行再抛出,不留"库里有引用、存储无对象"
  的孤儿;commit 在 storage.upload 之前,也不存在"对象已写、commit 失败"的
  反向孤儿。
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exceptions import ConflictError, NotFoundError
from app.common.storage import ObjectInfo, StorageClient, get_storage
from app.common.timeutil import now_bj
from app.models.enums import UploadPurpose
from app.models.sys_account import SysAccount
from app.models.sys_upload import SysUpload

# 占位撞号时的最大顺延次数(5 次意味着同 key 前缀下 ≥5 个并发同时撞号,超出视为异常冲突)
_SEQ_MAX_ATTEMPTS = 5

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


def _escape_like(s: str) -> str:
    """转义 LIKE 通配符(key 前缀里的 `_`/`%` 是用户可控内容,不能当通配符用)。"""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def _next_seq(db: AsyncSession, key_head: str) -> int:
    """同前缀已有上传数 + 1 作为初始序号(撞号由占位 insert 的唯一索引兜底)。"""
    stmt = select(func.count()).select_from(SysUpload).where(
        SysUpload.object_key.like(f"{_escape_like(key_head)}%", escape="\\")
    )
    count = (await db.execute(stmt)).scalar_one()
    return int(count) + 1


async def _occupy_key(
    db: AsyncSession, *, key: str, size: int,
    family_id: str, uploader: SysAccount,
    content_type: str, purpose: UploadPurpose,
    bucket: str, storage_provider: str, public_url: str | None,
) -> SysUpload:
    """插入占位行并 commit;object_key 唯一索引在此仲裁并发。"""
    record = SysUpload(
        family_id=family_id,
        uploader_account_id=uploader.id,
        storage_provider=storage_provider,
        object_key=key,
        bucket=bucket,
        public_url=public_url,
        content_type=content_type,
        size=size,
        purpose=purpose,
        etag=None,  # etag 由对象写入结果回填
    )
    db.add(record)
    await db.commit()
    return record


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
        from app.models.scn_task_instance import ScnTaskInstance
        task = await db.get(ScnTaskInstance, task_id)
        if task is None or task.family_id != family_id:
            raise NotFoundError(f"任务 {task_id} 不存在")
        task_no = task_id

    await storage.ensure_bucket()

    ext = _file_ext(filename, content_type)
    key_head = _key_head(storage, user_id=uploader.id, task_no=task_no)
    seq = await _next_seq(db, key_head)

    # 1) 先插库占位:并发撞号时唯一索引在这里裁决,败者顺延重试(不重写对象)
    for _attempt in range(_SEQ_MAX_ATTEMPTS):
        key = f"{key_head}{seq}.{ext}"
        try:
            record = await _occupy_key(
                db, key=key, size=len(content), family_id=family_id,
                uploader=uploader, content_type=content_type, purpose=purpose,
                bucket=storage.bucket, storage_provider=storage.provider_name,
                public_url=None,  # 占位阶段未知;local 模式写入成功后回填
            )
            break
        except IntegrityError:
            await db.rollback()
            seq += 1
    else:
        raise ConflictError("上传序号冲突,请重试")

    # 2) 占位成功后写对象;失败删除占位行,不留"有引用无对象"的孤儿
    try:
        info: ObjectInfo = await storage.upload(key, content, content_type=content_type)
    except Exception:
        await db.delete(record)
        await db.commit()
        raise

    # 3) 回填对象写入结果(etag;local 模式的稳定 URL)
    record.etag = info.etag
    access_url = storage.presign_get(info.key)
    # MinIO 预签名 URL 会过期,不落库;读取时按 object_key 现算(access_url 字段)。
    # local 模式 URL 稳定,落库即最终 URL。
    record.public_url = access_url if storage.provider_name == "local" else None
    await db.commit()
    await db.refresh(record)
    return record


def build_access_url(object_key: str, *, expires_seconds: int = 3600) -> str:
    storage = get_storage()
    return storage.presign_get(object_key, expires_seconds=expires_seconds)


async def get_upload(db: AsyncSession, upload_id: str) -> SysUpload:
    u = await db.get(SysUpload, upload_id)
    if not u:
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
