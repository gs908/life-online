"""对象存储公共接口。"""
from app.common.storage.base import ObjectInfo, StorageClient
from app.common.storage.factory import get_storage

__all__ = ["ObjectInfo", "StorageClient", "get_storage"]
