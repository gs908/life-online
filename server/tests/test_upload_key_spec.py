"""上传存储路径规范与 MinIO/local 双模式 URL 行为。

- 纯单元部分(不依赖数据库,始终执行):
  扩展名提取、key 前缀拼接(full_key)、local 预签名 URL 带 key 前缀、
  文件名安全化(DEV-30);
- DB 部分(远程数据库可达才执行):save_upload 全链路 ——
  task_proof 带任务上下文的路径规范(DEV-30)
  `用户/任务实例id/yyyymmdd/task_proof-序号_文件名.扩展名`、
  非任务路径规范(DEV-20)、序号自增、task_instance_id 落库与按任务检索、
  提交任务时回填绑定、跨家庭 task_id 拒绝。
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
    """非任务上传 key 前缀 = `{用户}/{年}/{月}/{日}/{purpose}-`(DEV-20 形状,北京时区当天)。"""
    storage = LocalFileStorage(str(tmp_path), bucket="local",
                               public_base_url="/api/v1/files", prefix="p")
    head = upload_service._key_head(storage, user_id="userA", task_no="avatar")
    today = now_bj()
    assert head == f"p/userA/{today.year:04d}/{today.month:02d}/{today.day:02d}/avatar-"


def test_task_key_head_matches_path_spec(tmp_path) -> None:
    """task_proof 带 task_id 的 key 前缀(DEV-30)= `{用户}/{任务实例id}/{yyyymmdd}/task_proof-`。"""
    storage = LocalFileStorage(str(tmp_path), bucket="local",
                               public_base_url="/api/v1/files", prefix="p")
    head = upload_service._task_key_head(storage, user_id="userA", task_instance_id="taskB")
    today = now_bj()
    assert head == f"p/userA/taskB/{today:%Y%m%d}/task_proof-"


# ---------- 纯单元:文件名安全化(DEV-30) ----------


def test_safe_stem_keeps_chinese_and_word_chars() -> None:
    # 中文是 unicode 字母,原样保留(键内可读);扩展名剥掉
    assert upload_service._safe_stem("整理书桌证明.jpg") == "整理书桌证明"
    assert upload_service._safe_stem("proof_final.png") == "proof_final"
    assert upload_service._safe_stem("证明.v2.jpeg") == "证明_v2"  # 只剥最后一个扩展名,内部点折叠


def test_safe_stem_collapses_spaces_and_special_chars() -> None:
    # 空格/标点/控制字符折叠为单个 _,首尾杂字符剥掉
    assert upload_service._safe_stem("my photo (1).png") == "my_photo_1"
    assert upload_service._safe_stem("  a???!@#b  .png") == "a_b"
    assert upload_service._safe_stem("a\x00b|c*.jpg") == "a_b_c"


def test_safe_stem_strips_path_components() -> None:
    # 路径分隔符(含反斜杠)只保留 basename,防止伪造目录段
    assert upload_service._safe_stem("../../etc/passwd.png") == "passwd"
    assert upload_service._safe_stem("C:\\Users\\laura\\桌面.png") == "桌面"
    assert upload_service._safe_stem("/etc/shadow") == "shadow"


def test_safe_stem_truncates_overlong_names() -> None:
    long_name = "x" * 500 + ".jpg"
    assert len(upload_service._safe_stem(long_name)) == upload_service._SAFE_STEM_MAX
    assert upload_service._safe_stem(long_name) == "x" * upload_service._SAFE_STEM_MAX


def test_safe_stem_falls_back_when_empty() -> None:
    # 去掉杂字符后为空 / 空文件名:兜底 file,保证键段非空
    assert upload_service._safe_stem("。。。") == "file"
    assert upload_service._safe_stem("   ") == "file"
    assert upload_service._safe_stem("") == "file"
    assert upload_service._safe_stem(".jpg") == "file"
    assert upload_service._safe_stem(".hidden.jpg") == "hidden"


# ---------- 纯单元:LIKE 转义与存量 URL 读取端忽略 ----------


def test_escape_like() -> None:
    # key 前缀里的 `_`/`%`/`\` 不能当通配符(purpose 里就有 `_`)
    assert upload_service._escape_like("task_proof/100%_a\\b") == "task\\_proof/100\\%\\_a\\\\b"


def test_effective_public_url_ignores_legacy_minio_rows() -> None:
    """存量回归:旧实现曾把 MinIO 预签名 URL 落库,读取端对 minio 行一律忽略。"""
    from types import SimpleNamespace

    from app.api.v1.uploads import _effective_public_url

    legacy_minio = SimpleNamespace(
        storage_provider="minio",
        public_url="http://minio:9000/life-online/x.jpg?X-Amz-Signature=stale",
    )
    assert _effective_public_url(legacy_minio) is None

    local = SimpleNamespace(storage_provider="local", public_url="/api/v1/files/a.jpg")
    assert _effective_public_url(local) == "/api/v1/files/a.jpg"

    # 旧代码曾把 settings.storage.provider 原样落库,local 家族的别名同样可信
    alias = SimpleNamespace(storage_provider="filestorage", public_url="/api/v1/files/b.jpg")
    assert _effective_public_url(alias) == "/api/v1/files/b.jpg"


# ---------- DB 集成:save_upload 全链路(local 模式) ----------


async def test_save_upload_follows_path_spec_and_increments_seq(
    db_session, seeded_family, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """task_proof 带 task_id(DEV-30):`用户/任务实例id/yyyymmdd/task_proof-序号_文件名.扩展名`。"""
    storage = LocalFileStorage(str(tmp_path), bucket="local",
                               public_base_url="/api/v1/files")
    monkeypatch.setattr(upload_service, "get_storage", lambda: storage)
    seed = seeded_family
    task_id = seed.task_instance.id
    user_id = seed.parent.id

    first = await upload_service.save_upload(
        db_session, family_id=seed.family.id, uploader=seed.parent,
        content=b"a", content_type="image/jpeg", purpose=UploadPurpose.TASK_PROOF,
        filename="整理书桌 证明.jpg", task_id=task_id,
    )
    today = now_bj()
    expected = f"{user_id}/{task_id}/{today:%Y%m%d}/task_proof-1_整理书桌_证明.jpg"
    assert first.object_key == expected
    assert first.task_instance_id == task_id
    assert first.public_url == f"/api/v1/files/{expected}"
    assert (tmp_path / expected).read_bytes() == b"a"

    second = await upload_service.save_upload(
        db_session, family_id=seed.family.id, uploader=seed.parent,
        content=b"b", content_type="image/jpeg", purpose=UploadPurpose.TASK_PROOF,
        filename="proof2.jpg", task_id=task_id,
    )
    assert second.object_key == f"{user_id}/{task_id}/{today:%Y%m%d}/task_proof-2_proof2.jpg"

    # 数据库层按任务检索(DEV-30):sys_upload.task_instance_id(顺序无关断言:id 是 uuid 非自增)
    found = await upload_service.find_uploads(
        db_session, family_id=seed.family.id, task_instance_id=task_id
    )
    assert {u.object_key for u in found} == {first.object_key, second.object_key}


async def test_save_upload_without_task_id_keeps_dev20_shape_and_binds_on_submit(
    db_session, seeded_family, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """未携带 task_id 的 task_proof:键保持 DEV-20 形状,task_instance_id 由提交任务回填。"""
    from app.models.enums import TaskStatus
    from app.services import task_service

    storage = LocalFileStorage(str(tmp_path), bucket="local",
                               public_base_url="/api/v1/files")
    monkeypatch.setattr(upload_service, "get_storage", lambda: storage)
    seed = seeded_family

    record = await upload_service.save_upload(
        db_session, family_id=seed.family.id, uploader=seed.child_account,
        content=b"c", content_type="image/jpeg", purpose=UploadPurpose.TASK_PROOF,
        filename="proof.jpg",
    )
    today = now_bj()
    assert record.object_key == (
        f"{seed.child_account.id}/{today.year:04d}/{today.month:02d}/{today.day:02d}/task_proof-1.jpg"
    )
    assert record.task_instance_id is None

    # 任务置为该孩子进行中,提交时回填绑定
    seed.task_instance.status = TaskStatus.IN_PROGRESS
    seed.task_instance.assignee_child_id = seed.child.id
    await db_session.commit()
    await task_service.submit_task(
        db_session, task_id=seed.task_instance.id, user=seed.child_account,
        proof_object_key=record.object_key,
    )
    await db_session.refresh(record)
    assert record.task_instance_id == seed.task_instance.id
    # 绑定后按任务可检索到该凭证
    found = await upload_service.find_uploads(
        db_session, family_id=seed.family.id, task_instance_id=seed.task_instance.id
    )
    assert {u.object_key for u in found} == {record.object_key}


async def test_submit_rejects_proof_already_bound_to_other_task(
    db_session, seeded_family, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """已绑定其他任务的凭证拒绝复用(防键含 A 任务 id、库却绑到 B 任务的错位)。"""
    from app.common.exceptions import ValidationError
    from app.models.enums import TaskStatus
    from app.models.scn_task_instance import ScnTaskInstance
    from app.services import task_service

    storage = LocalFileStorage(str(tmp_path), bucket="local",
                               public_base_url="/api/v1/files")
    monkeypatch.setattr(upload_service, "get_storage", lambda: storage)
    seed = seeded_family

    record = await upload_service.save_upload(
        db_session, family_id=seed.family.id, uploader=seed.child_account,
        content=b"d", content_type="image/jpeg", purpose=UploadPurpose.TASK_PROOF,
        filename="p.jpg",
    )
    seed.task_instance.status = TaskStatus.IN_PROGRESS
    seed.task_instance.assignee_child_id = seed.child.id
    # 造一个同家庭的其他任务,凭证绑定到它
    other = ScnTaskInstance(
        family_id=seed.family.id, season_id=seed.season.id,
        template_id=seed.task_template.id, title="他任务", status=TaskStatus.AVAILABLE,
    )
    db_session.add(other)
    await db_session.flush()
    record.task_instance_id = other.id
    await db_session.commit()

    with pytest.raises(ValidationError):
        await task_service.submit_task(
            db_session, task_id=seed.task_instance.id, user=seed.child_account,
            proof_object_key=record.object_key,
        )



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


async def test_save_upload_minio_mode_keeps_public_url_none(
    db_session, seeded_family, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MinIO 模式:预签名 URL 会过期,public_url 一律不落库(Mars 审查回归钉子)。"""
    storage = LocalFileStorage(str(tmp_path), bucket="life-online",
                               public_base_url="/api/v1/files")
    storage.provider_name = "minio"  # 复用本地落盘,只模拟 minio 的 URL 语义
    monkeypatch.setattr(upload_service, "get_storage", lambda: storage)
    seed = seeded_family

    record = await upload_service.save_upload(
        db_session, family_id=seed.family.id, uploader=seed.parent,
        content=b"m", content_type="image/jpeg", purpose=UploadPurpose.TASK_PROOF,
        filename="proof.jpg", task_id=seed.task_instance.id,
    )
    assert record.public_url is None
    assert record.storage_provider == "minio"
    # 对象本体仍正常写入
    assert (tmp_path / record.object_key).read_bytes() == b"m"


async def test_save_upload_cleans_placeholder_when_storage_fails(
    db_session, seeded_family, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """占位插入成功但对象写入失败:占位行删除,不留"有引用无对象"的孤儿。"""
    from sqlalchemy import select

    from app.models.sys_upload import SysUpload

    storage = LocalFileStorage(str(tmp_path), bucket="local",
                               public_base_url="/api/v1/files")

    async def _boom(key, data, *, content_type="application/octet-stream"):
        raise RuntimeError("storage down")

    storage.upload = _boom  # type: ignore[method-assign]
    monkeypatch.setattr(upload_service, "get_storage", lambda: storage)
    seed = seeded_family

    with pytest.raises(RuntimeError):
        await upload_service.save_upload(
            db_session, family_id=seed.family.id, uploader=seed.parent,
            content=b"x", content_type="image/jpeg", purpose=UploadPurpose.TASK_PROOF,
            filename="p.jpg", task_id=seed.task_instance.id,
        )

    keys = (
        await db_session.execute(
            select(SysUpload.object_key).where(SysUpload.family_id == seed.family.id)
        )
    ).scalars().all()
    assert keys == [], f"占位行应被清理,残留: {keys}"
