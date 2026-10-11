"""AI 能力配置 / 存储降级行为。

覆盖 DEV-24 的验收点:
- `ai` 三段(llm/image/video)各自独立配置模型与默认参数,key 不落 yaml;
- 各能力调用链路先过 `require_ai_capability`,未启用 / 未配置时报错清晰(503);
- LLM 客户端默认参数来自 yaml,请求级可覆盖。

不依赖数据库,始终执行(不受远程数据库是否可达影响)。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.common.ai import require_ai_capability
from app.common.exceptions import ServiceUnavailableError
from app.common.llm.factory import get_llm_client
from app.common.llm.openai_compat import OpenAICompatClient
from app.common.storage.factory import get_storage
from app.config import (
    AICapabilitySection,
    ImageCapabilitySection,
    LLMCapabilitySection,
    StorageMinioSection,
    VideoCapabilitySection,
    settings,
)


def test_ai_capability_section_is_configured() -> None:
    assert not AICapabilitySection().is_configured
    assert not AICapabilitySection(base_url="http://x", api_key="", model="m").is_configured
    assert AICapabilitySection(base_url="http://x", api_key="k", model="m").is_configured


def test_ai_sections_have_independent_default_params() -> None:
    """三段结构落地:各能力独立指定 provider/model 与各自的默认参数形状。"""
    assert settings.ai.llm.enabled is True
    assert settings.ai.llm.default_params.temperature == pytest.approx(0.7)
    assert settings.ai.llm.default_params.timeout_s > 0
    assert settings.ai.image.enabled is False
    assert settings.ai.image.default_params.n == 1
    assert settings.ai.video.enabled is False
    assert settings.ai.video.default_params.resolution == "720p"


def test_yaml_never_carries_plaintext_ai_keys() -> None:
    """key 一律经环境变量引用:yaml 里的每个 api_key 必须是 ${env:...} 占位。"""
    raw = (Path(__file__).resolve().parent.parent / "config.yaml").read_text(encoding="utf-8")
    ai_block = raw.split("ai:", 1)[1]
    for line in ai_block.splitlines():
        if "api_key:" in line:
            assert "${env:" in line, f"config.yaml 出现疑似明文 key: {line.strip()}"


def test_minio_section_is_configured() -> None:
    assert not StorageMinioSection().is_configured
    assert not StorageMinioSection(endpoint="h:9000").is_configured
    assert StorageMinioSection(endpoint="h:9000", access_key="a", secret_key="s").is_configured


def _unset_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings.ai.llm, "base_url", "")
    monkeypatch.setattr(settings.ai.llm, "api_key", "")
    monkeypatch.setattr(settings.ai.llm, "model", "")


def test_get_llm_client_raises_clear_error_when_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    get_llm_client.cache_clear()
    _unset_llm(monkeypatch)
    try:
        with pytest.raises(ServiceUnavailableError) as exc_info:
            get_llm_client()
        assert exc_info.value.http_status == 503
        assert "AI_LLM_API_KEY" in exc_info.value.message
        assert "ai.llm" in exc_info.value.message or "AI_LLM_BASE_URL" in exc_info.value.message
    finally:
        get_llm_client.cache_clear()


def test_llm_disabled_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """enabled=false 时,即便字段齐全也必须报"未启用"而不是走到调用。"""
    cfg = LLMCapabilitySection(
        enabled=False, base_url="http://x", api_key="k", model="m"
    )
    monkeypatch.setattr(settings.ai, "llm", cfg)
    get_llm_client.cache_clear()
    try:
        with pytest.raises(ServiceUnavailableError) as exc_info:
            get_llm_client()
        assert exc_info.value.http_status == 503
        assert "未启用" in exc_info.value.message
        assert "ai.llm.enabled" in exc_info.value.message
    finally:
        get_llm_client.cache_clear()


@pytest.mark.parametrize(
    "name, section",
    [
        ("image", ImageCapabilitySection),
        ("video", VideoCapabilitySection),
    ],
)
def test_media_capabilities_gate_clear_errors(
    name: str, section: type, monkeypatch: pytest.MonkeyPatch
) -> None:
    """image / video 调用链路各自读取配置:未启用、启用但未配置,报错都清晰。"""
    # 未启用(yaml 默认状态):报"未启用" + 对应段名
    monkeypatch.setattr(settings.ai, name, section())
    with pytest.raises(ServiceUnavailableError) as exc_info:
        require_ai_capability(name)  # type: ignore[arg-type]
    assert exc_info.value.http_status == 503
    assert f"ai.{name}.enabled" in exc_info.value.message

    # 启用但未配置:报"未配置" + 对应环境变量名
    monkeypatch.setattr(settings.ai, name, section(enabled=True))
    with pytest.raises(ServiceUnavailableError) as exc_info:
        require_ai_capability(name)  # type: ignore[arg-type]
    assert f"AI_{name.upper()}_API_KEY" in exc_info.value.message

    # 启用且配置齐全:返回该能力配置段
    configured = section(enabled=True, base_url="http://x", api_key="k", model="m")
    monkeypatch.setattr(settings.ai, name, configured)
    assert require_ai_capability(name) is configured  # type: ignore[arg-type]


def test_llm_client_uses_yaml_default_params(monkeypatch: pytest.MonkeyPatch) -> None:
    """工厂把 yaml 默认参数注入客户端;请求级传参可覆盖。"""
    cfg = LLMCapabilitySection(
        enabled=True,
        base_url="http://x",
        api_key="k",
        model="m",
        default_params={
            "temperature": 0.2,
            "max_tokens": 128,
            "timeout_s": 5,
            "max_retries": 0,
        },
    )
    monkeypatch.setattr(settings.ai, "llm", cfg)
    get_llm_client.cache_clear()
    try:
        client = get_llm_client()
        assert isinstance(client, OpenAICompatClient)
        resolved_t, resolved_mtls = client._resolve_params(None, None)
        assert resolved_t == pytest.approx(0.2)
        assert resolved_mtls == 128
        assert client._resolve_params(0.9, 512) == (pytest.approx(0.9), 512)
    finally:
        get_llm_client.cache_clear()


def test_get_storage_raises_clear_error_when_minio_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    get_storage.cache_clear()
    monkeypatch.setattr(settings.storage, "provider", "minio")
    monkeypatch.setattr(settings.storage.minio, "endpoint", "")
    monkeypatch.setattr(settings.storage.minio, "access_key", "")
    monkeypatch.setattr(settings.storage.minio, "secret_key", "")
    try:
        with pytest.raises(ServiceUnavailableError) as exc_info:
            get_storage()
        assert exc_info.value.http_status == 503
        assert "STORAGE_PROVIDER" in exc_info.value.message
    finally:
        get_storage.cache_clear()


def test_get_storage_local_provider_never_needs_minio_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """local 是 MinIO 未配置时可用的降级方案:仅需切换 STORAGE_PROVIDER,无需任何密钥。"""
    get_storage.cache_clear()
    monkeypatch.setattr(settings.storage, "provider", "local")
    monkeypatch.setattr(settings.storage.local, "root_path", str(tmp_path))
    try:
        storage = get_storage()
        assert storage is not None
    finally:
        get_storage.cache_clear()


def _make_minio_storage_with_stub_client(monkeypatch: pytest.MonkeyPatch, exc: Exception):
    """构造底层连接注入指定异常的 MinIOStorage —— 不碰真实网络。"""
    from app.common.storage.minio import MinIOStorage

    storage = MinIOStorage(
        endpoint="localhost:9000", access_key="a", secret_key="s",
        bucket="life-online",
    )

    class _StubClient:
        def bucket_exists(self, bucket: str) -> bool:
            raise exc

    monkeypatch.setattr(storage, "_client", _StubClient())
    return storage


async def test_minio_conn_error_translated_to_503(monkeypatch: pytest.MonkeyPatch) -> None:
    """DEV-28:MinIO 配置了但连不上 → StorageUnavailableError(503),不裸 500。

    用 stub 客户端注入 urllib3.MaxRetryError(业主本地 500 的原始异常形态),
    断言翻译层的判定与文案。
    """
    from urllib3.connectionpool import HTTPConnectionPool
    from urllib3.exceptions import MaxRetryError

    from app.common.exceptions import StorageUnavailableError

    raw = MaxRetryError(HTTPConnectionPool(host="localhost", port=9000), "/life-online?location=")
    storage = _make_minio_storage_with_stub_client(monkeypatch, raw)

    with pytest.raises(StorageUnavailableError) as exc_info:
        await storage.ensure_bucket()
    assert exc_info.value.http_status == 503
    assert exc_info.value.code == "storage_unavailable"
    assert "STORAGE_PROVIDER=local" in exc_info.value.message
    assert "localhost:9000" in exc_info.value.message


async def test_minio_s3_error_not_translated(monkeypatch: pytest.MonkeyPatch) -> None:
    """S3Error(服务在、请求被拒,如权限)不是"不可达",必须原样上抛给上层处理。"""
    from minio.error import S3Error

    from app.common.exceptions import StorageUnavailableError

    s3_err = S3Error(
        code="AccessDenied", message="denied", resource="bucket", request_id="r",
        host_id="h", response=None,
    )
    storage = _make_minio_storage_with_stub_client(monkeypatch, s3_err)

    with pytest.raises(S3Error) as exc_info:
        await storage.ensure_bucket()
    assert not isinstance(exc_info.value, StorageUnavailableError)


def test_minio_presign_get_passes_timedelta_to_sdk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DEV-28 缺陷③:minio-py 7.x 的 expires 要求 timedelta(内部 total_seconds() 校验),
    传 int 会 AttributeError。mock SDK 断言实际传入的是 timedelta 且秒数正确。"""
    from datetime import timedelta

    from app.common.storage.minio import MinIOStorage

    storage = MinIOStorage(
        endpoint="localhost:9000", access_key="a", secret_key="s",
        bucket="life-online",
    )
    captured: dict = {}

    class _StubClient:
        def presigned_get_object(self, bucket, key, *, expires, **kwargs):
            captured["bucket"], captured["key"], captured["expires"] = bucket, key, expires
            return "http://signed-url"

    monkeypatch.setattr(storage, "_client", _StubClient())

    # 默认 3600s
    assert storage.presign_get("a/b.jpg") == "http://signed-url"
    assert captured["bucket"] == "life-online"
    assert captured["key"] == "a/b.jpg"
    assert captured["expires"] == timedelta(seconds=3600)

    # 自定义秒数
    storage.presign_get("a/b.jpg", expires_seconds=120)
    assert captured["expires"] == timedelta(seconds=120)


def test_minio_presign_get_real_sdk_succeeds_with_region() -> None:
    """真实 SDK 冒烟(非 mock):配置 region 后签名是纯本地 SigV4 计算,无需网络。

    若 expires 类型回退成 int,SDK 内部 `expires.total_seconds()` 会立刻
    AttributeError —— 用例不依赖 MinIO 服务,可稳定复现缺陷③。
    """
    from app.common.storage.minio import MinIOStorage

    storage = MinIOStorage(
        endpoint="localhost:9000", access_key="a", secret_key="s",
        bucket="life-online", region="us-east-1",
    )
    url = storage.presign_get("u1/2026/10/11/task-1.jpg")
    assert "X-Amz-Signature" in url, "应返回带签名的 GET URL"
    assert "u1%2F2026%2F10%2F11%2Ftask-1.jpg" in url or "task-1.jpg" in url
