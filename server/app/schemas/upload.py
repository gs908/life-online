"""上传 DTO。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.models.enums import UploadPurpose


class UploadRead(BaseModel):
    id: str
    family_id: str
    uploader_account_id: str | None = None
    storage_provider: str
    object_key: str
    bucket: str
    public_url: str | None = None
    content_type: str
    size: int
    purpose: UploadPurpose
    access_url: str
    created_at: datetime


class UploadUrlRequest(BaseModel):
    """前端预先请求一个上传位置(后续用于前端直传对象存储)。

    当前未启用直传,前端走后端代收;保留该 DTO 为后续直传留接口。
    """
    purpose: UploadPurpose = UploadPurpose.OTHER
    content_type: str = "application/octet-stream"
    ext: str | None = None
