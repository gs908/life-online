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
    """对象存储客户端统一接口。

    对象 key 统一约定:`{key_prefix}/{业务相对路径}`。
    key_prefix 来自 yaml 配置(minio.prefix / local.prefix),可空;
    bucket 由各实现自持,不在 key 内(完整定位 = bucket + key)。
    """

    #: 存储模式标识("minio" / "local"),业务层按其区分 URL 稳定性等行为
    provider_name: str = ""

    #: 配置的对象 key 前缀(yaml 管理),空串表示无前缀
    key_prefix: str = ""

    def full_key(self, relative_key: str) -> str:
        """把业务相对路径拼成带前缀的完整对象 key(过滤空段,避免 `//`)。"""
        parts = [p.strip("/") for p in (self.key_prefix, relative_key.strip("/")) if p.strip("/")]
        return "/".join(parts)

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
