"""
MinIO 客户端实现(兼容 S3 协议)。

- 上传/删除走 to_thread 包装的同步 minio-py(简单稳定)
- 预签名 URL 同步生成即可
- 连接失败(服务未启动/网络不通)统一翻译成 StorageUnavailableError(503),
  不让 urllib3 底层异常裸冒成 500(DEV-28)
"""
from __future__ import annotations

import asyncio
from functools import partial

from minio import Minio
from minio.error import S3Error
from urllib3.exceptions import HTTPError as Urllib3HTTPError

from app.common.exceptions import StorageUnavailableError
from app.common.storage.base import ObjectInfo, StorageClient

# 判定"存储不可达"的异常家族:
# - urllib3 HTTPError: minio-py 的请求经 urllib3 发出,连接被拒/中断会以
#   MaxRetryError(内包 ProtocolError/RemoteDisconnected)形态冒出;
# - OSError: socket 层错误(ConnectionError / timeout 等)的公共基类。
# S3Error(服务在、但请求本身被拒,如 NoSuchBucket/权限)不属于"不可达",原样上抛。
_CONN_ERRORS = (Urllib3HTTPError, OSError)


class MinIOStorage(StorageClient):
    def __init__(self, endpoint: str, access_key: str, secret_key: str,
                 bucket: str, *, secure: bool = False, prefix: str = "") -> None:
        self._endpoint = endpoint
        self._client = Minio(
            endpoint=endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )
        self.bucket = bucket
        self.key_prefix = prefix.strip("/")
        self.provider_name = "minio"

    def _translate(self, exc: Exception, op: str) -> Exception:
        """连接类异常转 503 降级错误;其余(S3Error 等)原样返回交由上层处理。"""
        if not isinstance(exc, _CONN_ERRORS):
            return exc
        return StorageUnavailableError(
            f"对象存储不可用,请检查 MinIO 服务({self._endpoint})是否运行,"
            f"或切换 STORAGE_PROVIDER=local 使用本地文件存储。"
            f"(操作: {op}; 原因: {exc!r})"
        )

    async def ensure_bucket(self) -> None:
        def _ensure() -> None:
            if not self._client.bucket_exists(self.bucket):
                self._client.make_bucket(self.bucket)
        try:
            await asyncio.to_thread(_ensure)
        except Exception as e:
            raise self._translate(e, "ensure_bucket") from e

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
                self.bucket,
                key,
                BytesIO(data),
                length=len(data),
                content_type=content_type,
            )
            return result.etag, result.version_id

        try:
            etag, _ = await asyncio.to_thread(_put)
        except Exception as e:
            raise self._translate(e, f"put {key}") from e
        return ObjectInfo(
            bucket=self.bucket,
            key=key,
            size=len(data),
            content_type=content_type,
            etag=etag,
        )

    async def delete(self, key: str) -> None:
        try:
            await asyncio.to_thread(partial(self._client.remove_object, self.bucket, key))
        except S3Error as e:
            if e.code in ("NoSuchKey", "NoSuchObject"):
                return
            raise
        except Exception as e:
            raise self._translate(e, f"remove {key}") from e

    def presign_get(self, key: str, *, expires_seconds: int = 3600) -> str:
        return self._client.presigned_get_object(
            self.bucket, key, expires=expires_seconds,
        )
