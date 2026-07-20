"""
对象存储抽象接口。

业务层只依赖此抽象,不直接 import 具体实现。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class ObjectInfo:
    bucket: str
    key: str
    size: int
    content_type: str | None = None
    etag: str | None = None

    @property
    def uri(self) -> str:
        return f"s3://{self.bucket}/{self.key}"


class StorageClient(ABC):
    """对象存储客户端统一接口。"""

    @abstractmethod
    async def ensure_bucket(self) -> None:
        """启动时确保 bucket 存在。"""

    @abstractmethod
    async def upload(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str = "application/octet-stream",
    ) -> ObjectInfo:
        """上传对象,返回 ObjectInfo(含 URI)。"""

    @abstractmethod
    async def delete(self, key: str) -> None:
        """删除对象。"""

    @abstractmethod
    def presign_get(
        self,
        key: str,
        *,
        expires_seconds: int = 3600,
    ) -> str:
        """生成 GET 预签名 URL(私有对象访问用)。"""
