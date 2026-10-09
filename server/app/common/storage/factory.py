"""
存储工厂。

根据 settings.storage.provider 选择具体实现,支持 minio / local。
"""
from __future__ import annotations

from functools import lru_cache

from app.common.exceptions import ServiceUnavailableError
from app.common.storage.base import StorageClient
from app.common.storage.local import LocalFileStorage
from app.common.storage.minio import MinIOStorage
from app.config import settings


@lru_cache
def get_storage() -> StorageClient:
    provider = settings.storage.provider.lower()
    if provider == "minio":
        m = settings.storage.minio
        if not m.is_configured:
            raise ServiceUnavailableError(
                "对象存储未配置:MinIO 缺少 MINIO_ENDPOINT / MINIO_ACCESS_KEY / MINIO_SECRET_KEY。"
                "请补全配置,或将 STORAGE_PROVIDER 切换为 local 使用本地文件存储降级方案。"
            )
        return MinIOStorage(
            endpoint=m.endpoint,
            access_key=m.access_key,
            secret_key=m.secret_key,
            bucket=m.bucket,
            secure=m.secure,
        )
    if provider in {"local", "filestorage", "file"}:
        local = settings.storage.local
        return LocalFileStorage(
            root_path=local.root_path,
            bucket=local.bucket,
            public_base_url=local.public_base_url,
        )
    raise ValueError(f"不支持的 storage provider: {settings.storage.provider}")
