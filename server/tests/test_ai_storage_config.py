"""time-coins / upload / AI 闭环里 LLM、MinIO 未配置时的降级行为。

不依赖数据库,始终执行(不受远程数据库是否可达影响)。
"""
from __future__ import annotations

import pytest

from app.common.exceptions import ServiceUnavailableError
from app.common.llm.factory import get_llm_client
from app.common.storage.factory import get_storage
from app.config import LLMSection, StorageMinioSection, settings


def test_llm_section_is_configured() -> None:
    assert not LLMSection(base_url="", api_key="", model="").is_configured
    assert not LLMSection(base_url="http://x", api_key="", model="m").is_configured
    assert LLMSection(base_url="http://x", api_key="k", model="m").is_configured


def test_minio_section_is_configured() -> None:
    assert not StorageMinioSection().is_configured
    assert not StorageMinioSection(endpoint="h:9000").is_configured
    assert StorageMinioSection(endpoint="h:9000", access_key="a", secret_key="s").is_configured


def test_get_llm_client_raises_clear_error_when_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    get_llm_client.cache_clear()
    monkeypatch.setattr(settings.llm, "base_url", "")
    monkeypatch.setattr(settings.llm, "api_key", "")
    monkeypatch.setattr(settings.llm, "model", "")
    try:
        with pytest.raises(ServiceUnavailableError) as exc_info:
            get_llm_client()
        assert exc_info.value.http_status == 503
        assert "LLM_API_KEY" in exc_info.value.message
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
