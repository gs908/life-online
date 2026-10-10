"""DEV-20 上传存储路径规范与 MinIO/local 双模式 URL 行为。

- 纯单元部分(不依赖数据库,始终执行):
  扩展名提取、key 前缀拼接(full_key)、local 预签名 URL 带 key 前缀;
- DB 部分(远程数据库可达才执行):save_upload 全链路 ——
  路径规范 `用户/年/月/日/任务号-序号.扩展名`、序号自增、跨家庭 task_id 拒绝。
"""
from __future__ import annotations

import pytest

from app.common.exceptions import NotFoundError
from app.common.storage.local import LocalFileStorage
from app.common.timeutil import now_bj
from app.models.enums import UploadPurpose
from app.services import upload_service

# ---------- 纯单元:扩展名提取 ----------

def test_file_ext_from_filename() -> None:
    assert upload_service._file_ext("photo.JPG", "image/jpeg") == "jpg"
    assert upload_service._file_ext("a/b/c/video.mp4", "video/mp4") == "mp4"

def test_file_ext_sanitizes_dangerous_suffix() -> None:
    # 扩展名只保留字母数字:不携带路径分隔符/控制字符
    assert upload_service._file_ext("x.a/b", "text/plain") == "bin"  # basename 无后缀
    assert "/" not in upload_service._file_ext("x.p/hp", "text/plain")
    assert upload_service._file_ext("evil.php\x00.png", "image/png") == "png"

def test_file_ext_falls_back_to_content_type() -> None:
    assert upload_service._file_ext("noext", "image/jpeg") == "jpg"
    assert upload_service._file_ext("", "IMAGE/PNG;charset=utf8") == "png"
    assert upload_service._file_ext("noext", "application/octet-stream") == "bin"


# ---------- 纯单元:key 前缀与 local URL 行为 ----------

def test_full_key_prepends_configured_prefix(tmp_path) -> None:
    storage = LocalFileStorage(str(tmp_path), bucket="local",
                               public_base_url="/api/v1/files", prefix="prod")
    assert storage.full_key("u1/2026/10/10/task-1.jpg") == "prod/u1/2026/10/10/task-1.jpg"

def test_full_key_without_prefix_has_no_leading_slash(tmp_path) -> None:
    storage = LocalFileStorage(str(tmp_path), bucket="local",
                               public_base_url="/api/v1/files")
    assert storage.full_key("/u1/2026/10/10/task-1.jpg") == "u1/2026/10/10/task-1.jpg"

def test_local_presign_url_contains_prefix_and_key(tmp_path) -> None:
    storage = LocalFileStorage(str(tmp_path), bucket="local",
                               public_base_url="/api/v1/files", prefix="prod")
    url = storage.presign_get("prod/u1/2026/10/10/task-1.jpg")
    assert url == "/api/v1/files/prod/u1/2026/10/10/task-1.jpg"

def test_key_head_matches_path_spec(tmp_path) -> None:
    """key 前缀 = `{用户}/{年}/{月}/{日}/{任务号}-`(北京时区当天)。"""
    storage = LocalFileStorage(str(tmp_path), bucket="local",
                               public_base_url="/api/v1/files", prefix="p")
    head = upload_service._key_head(storage, user_id="userA", task_no="taskB")
    today = now_bj()
    assert head == f"p/userA/{today.year:04d}/{today.month:02d}/{today.day:02d}/taskB-"


# ---------- DB 集成:save_upload 全链路(local 模式) ----------


async def test_save_upload_follows_path_spec_and_increments_seq(
    db_session, seeded_family, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = LocalFileStorage(str(tmp_path), bucket="local",
                               public_base_url="/api/v1/files")
    monkeypatch.setattr(upload_service, "get_storage", lambda: storage)
    seed = seeded_family
    task_id = seed.task_instance.id
    user_id = seed.parent.id

    first = await upload_service.save_upload(
        db_session, family_id=seed.family.id, uploader=seed.parent,
        content=b"a", content_type="image/jpeg", purpose=UploadPurpose.TASK_PROOF,
        filename="proof.jpg", task_id=task_id,
    )
    today = now_bj()
    expected = f"{user_id}/{today.year:04d}/{today.month:02d}/{today.day:02d}/{task_id}-1.jpg"
    assert first.object_key == expected
    assert first.public_url == f"/api/v1/files/{expected}"
    assert (tmp_path / expected).read_bytes() == b"a"

    second = await upload_service.save_upload(
        db_session, family_id=seed.family.id, uploader=seed.parent,
        content=b"b", content_type="image/jpeg", purpose=UploadPurpose.TASK_PROOF,
        filename="proof2.jpg", task_id=task_id,
    )
    assert second.object_key == expected.replace("-1.jpg", "-2.jpg")



async def test_save_upload_without_task_uses_purpose_slug(
    db_session, seeded_family, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = LocalFileStorage(str(tmp_path), bucket="local",
                               public_base_url="/api/v1/files")
    monkeypatch.setattr(upload_service, "get_storage", lambda: storage)
    seed = seeded_family

    record = await upload_service.save_upload(
        db_session, family_id=seed.family.id, uploader=seed.parent,
        content=b"c", content_type="image/png", purpose=UploadPurpose.AVATAR,
        filename="me.png",
    )
    today = now_bj()
    assert record.object_key.endswith(
        f"{seed.parent.id}/{today.year:04d}/{today.month:02d}/{today.day:02d}/avatar-1.png"
    )



async def test_save_upload_rejects_task_from_other_family(
    db_session, seeded_family, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = LocalFileStorage(str(tmp_path), bucket="local",
                               public_base_url="/api/v1/files")
    monkeypatch.setattr(upload_service, "get_storage", lambda: storage)
    seed = seeded_family

    with pytest.raises(NotFoundError):
        await upload_service.save_upload(
            db_session, family_id="00000000-0000-0000-0000-000000000000",
            uploader=seed.parent, content=b"d", content_type="image/jpeg",
            purpose=UploadPurpose.TASK_PROOF, filename="x.jpg",
            task_id=seed.task_instance.id,
        )
