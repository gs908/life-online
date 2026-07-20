"""
MinIO 客户端实现(兼容 S3 协议)。

- 上传/删除走 to_thread 包装的同步 minio-py(简单稳定)
- 预签名 URL 同步生成即可
"""
from __future__ import annotations

import asyncio
from functools import partial

from minio import Minio
from minio.error import S3Error

from app.common.storage.base import ObjectInfo, StorageClient


class MinIOStorage(StorageClient):
    def __init__(self, endpoint: str, access_key: str, secret_key: str,
                 bucket: str, *, secure: bool = False) -> None:
        self._client = Minio(
            endpoint=endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )
        self._bucket = bucket

    async def ensure_bucket(self) -> None:
        def _ensure() -> None:
            if not self._client.bucket_exists(self._bucket):
                self._client.make_bucket(self._bucket)
        await asyncio.to_thread(_ensure)

    async def upload(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str = "application/octet-stream",
    ) -> ObjectInfo:
        from io import BytesIO

        def _put() -> tuple[str, str]:
            result = self._client.put_object(
                self._bucket,
                key,
                BytesIO(data),
                length=len(data),
                content_type=content_type,
            )
            return result.etag, result.version_id

        etag, _ = await asyncio.to_thread(_put)
        return ObjectInfo(
            bucket=self._bucket,
            key=key,
            size=len(data),
            content_type=content_type,
            etag=etag,
        )

    async def delete(self, key: str) -> None:
        try:
            await asyncio.to_thread(partial(self._client.remove_object, self._bucket, key))
        except S3Error as e:
            if e.code in ("NoSuchKey", "NoSuchObject"):
                return
            raise

    def presign_get(self, key: str, *, expires_seconds: int = 3600) -> str:
        return self._client.presigned_get_object(
            self._bucket, key, expires=expires_seconds,
        )
