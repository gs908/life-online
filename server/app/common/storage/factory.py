"""
存储工厂。

根据 settings.storage.provider 选择具体实现,支持 minio / local。
"""
from __future__ import annotations

from functools import lru_cache

from app.common.storage.base import StorageClient
from app.common.storage.local import LocalFileStorage
from app.common.storage.minio import MinIOStorage
from app.config import settings


@lru_cache
def get_storage() -> StorageClient:
    provider = settings.storage.provider.lower()
    if provider == "minio":
        m = settings.storage.minio
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
