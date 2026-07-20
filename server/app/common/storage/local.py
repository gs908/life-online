"""本地文件存储实现。

用于 demo / 本地开发场景,接口保持与对象存储一致。
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from urllib.parse import quote

from app.common.storage.base import ObjectInfo, StorageClient


class LocalFileStorage(StorageClient):
    def __init__(self, root_path: str, bucket: str, public_base_url: str) -> None:
        self._root = Path(root_path).resolve()
        self._bucket = bucket
        self._public_base_url = public_base_url.rstrip("/")

    async def ensure_bucket(self) -> None:
        await asyncio.to_thread(self._root.mkdir, parents=True, exist_ok=True)

    def _path_for(self, key: str) -> Path:
        root = self._root
        path = (root / key).resolve()
        if root != path and root not in path.parents:
            raise ValueError("非法文件 key")
        return path

    async def upload(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str = "application/octet-stream",
    ) -> ObjectInfo:
        path = self._path_for(key)

        def _write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

        await asyncio.to_thread(_write)
        return ObjectInfo(
            bucket=self._bucket,
            key=key,
            size=len(data),
            content_type=content_type,
            etag=None,
        )

    async def delete(self, key: str) -> None:
        path = self._path_for(key)
        if path.exists():
            await asyncio.to_thread(path.unlink)

    def presign_get(self, key: str, *, expires_seconds: int = 3600) -> str:
        encoded = quote(key.replace("\\", "/"), safe="/")
        return f"{self._public_base_url}/{encoded}"
