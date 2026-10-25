"""DEV-60:任务要点 → 任务建议(`POST /scn/tasks/generate-from-brief`)。

覆盖四类验收点:

- **schema 加法扩展**:`QUEST_JSON_SCHEMA` 增加 `difficulty` / `time_deposit`,
  但 `required` 集合不变 —— `POST /scn/ai/generate-quest` 的既有契约不受影响
  (老调用方只读 title/description/lore_snippet/xp_reward/type,多出来的字段
  被忽略);
- **确定性收敛**:LLM 输出无强约束,`normalize_quest_suggestion` 保证出参恒为
  5 个字段,缺字段取中性值、越界 clamp、押金按当日配额封顶;
- **失败口径**(docs/15 R12 同源):能力未启用/未配置保持 503;超时、非法
  JSON、结构非法一律 502 `external_service_error`,不裸 500;
- **路由契约**:路径/鉴权/入参校验与 handler 出参。

LLM 一律用假客户端,不触网;不依赖数据库的用例始终执行,需要数据库的用例
(鉴权后的 200/403/422 路径)由 `db_ready` 在库不可达时跳过。
"""
from __future__ import annotations

import asyncio
from datetime import timedelta
from types import SimpleNamespace

import pytest
from httpx import AsyncClient

from app.common.exceptions import ExternalServiceError, ServiceUnavailableError
from app.common.llm.types import LLMJsonResponse
from app.common.timeutil import today_bj
from app.config import settings
from app.dev.seed import SeededFamily
from app.schemas.common import ApiResponse
from app.schemas.task import TaskBriefGenerateRequest, TaskBriefSuggestion
from app.services import ai_service


def _auth_headers(account) -> dict[str, str]:
    from app.services import auth_service

    tokens = auth_service.issue_token_pair(account)
    return {"Authorization": f"Bearer {tokens.access_token}"}


# ---- 假 LLM 客户端 -------------------------------------------------------


class FakeQuestClient:
    """统计调用次数并回放指定 payload 的假客户端,不触网。"""

    def __init__(self, *, data=None, error: Exception | None = None, delay: float = 0.0):
        self.data = data if data is not None else {
            "title": "晨光中的委托",
            "description": "把口算 4 页做完,100 以内加减",
            "lore_snippet": "酒馆门前的告示板钉着一张新委托。",
            "xp_reward": 120,
            "type": "DAILY",
            "difficulty": 3,
            "time_deposit": 12,
        }
        self.error = error
        self.delay = delay
        self.calls = 0
        self.json_schemas: list[dict] = []

    async def chat_json(self, messages, json_schema=None, *, temperature=None):
        self.calls += 1
        self.json_schemas.append(json_schema or {})
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error is not None:
            raise self.error
        # 非 dict payload 不能塞进 LLMJsonResponse(data: dict),用 SimpleNamespace
        # 模拟"网关返回了结构非法的东西"(与 test_task_content 的坏形状用例同法)。
        if isinstance(self.data, dict):
            return LLMJsonResponse(data=self.data, raw={"usage": {"total_tokens": 7}})
        return SimpleNamespace(data=self.data, raw={"usage": {"total_tokens": 7}})


def _patch_llm(monkeypatch, fake) -> None:
    """业务层只经 ai_service 取客户端,故在 ai_service 层注入假实现。"""
    monkeypatch.setattr(ai_service, "get_llm_client", lambda: fake)


# ---- 1. schema 加法扩展(向后兼容) --------------------------------------


def test_quest_schema_is_extended_additively():
    """新字段进 properties,`required` 保持不变 —— 老接口契约不动。"""
    props = ai_service.QUEST_JSON_SCHEMA["properties"]
    assert props["difficulty"] == {"type": "integer", "minimum": 1, "maximum": 5}
    assert props["time_deposit"] == {"type": "integer", "minimum": 0}
    assert ai_service.QUEST_JSON_SCHEMA["required"] == [
        "title", "description", "lore_snippet", "xp_reward", "type",
    ]


def test_brief_schema_requires_the_two_new_numbers():
    """brief 专用 schema 在公共 schema 之上把两个数值字段列为必需。"""
    assert ai_service.BRIEF_QUEST_JSON_SCHEMA["required"] == [
        "title", "description", "lore_snippet", "xp_reward", "type",
        "difficulty", "time_deposit",
    ]
    # 基础字段与约束同源(不是各写一份)
    assert ai_service.BRIEF_QUEST_JSON_SCHEMA["properties"] is ai_service.QUEST_JSON_SCHEMA["properties"]
    # 公共 schema 未被就地修改
    assert "difficulty" not in ai_service.QUEST_JSON_SCHEMA["required"]


# ---- 2. 确定性收敛 -------------------------------------------------------


def test_normalize_keeps_valid_numbers():
    out = ai_service.normalize_quest_suggestion({
        "title": "  打扫房间  ", "description": "把书桌收拾干净",
        "xp_reward": 80, "difficulty": 4, "time_deposit": 15,
    })
    assert out == {
        "title": "打扫房间", "description": "把书桌收拾干净",
        "xp_reward": 80, "difficulty": 4, "time_deposit": 15,
    }


def test_normalize_fills_missing_numbers_with_neutral_defaults():
    out = ai_service.normalize_quest_suggestion({"title": "T", "description": "D"})
    assert out["xp_reward"] == ai_service.DEFAULT_QUEST_XP
    assert out["difficulty"] == 1
    assert out["time_deposit"] == 0


def test_normalize_clamps_out_of_range_numbers():
    out = ai_service.normalize_quest_suggestion({
        "title": "T", "description": "D",
        "xp_reward": -5, "difficulty": 9, "time_deposit": -3,
    })
    assert out["xp_reward"] == 0
    assert out["difficulty"] == 5
    assert out["time_deposit"] == 0

    out = ai_service.normalize_quest_suggestion({
        "title": "T", "description": "D", "difficulty": 0,
    })
    assert out["difficulty"] == 1


def test_normalize_caps_deposit_by_daily_quota():
    """目标日配额封顶(与 preview-deposit 的 for_date 同源)。"""
    out = ai_service.normalize_quest_suggestion(
        {"title": "T", "description": "D", "time_deposit": 999}, deposit_cap=50,
    )
    assert out["time_deposit"] == 50
    # 未超上限时原样保留
    out = ai_service.normalize_quest_suggestion(
        {"title": "T", "description": "D", "time_deposit": 7}, deposit_cap=50,
    )
    assert out["time_deposit"] == 7


def test_normalize_rejects_unusable_payloads():
    for bad in (["not", "a", "dict"], None):
        with pytest.raises(ExternalServiceError) as exc:
            ai_service.normalize_quest_suggestion(bad)
        assert exc.value.http_status == 502
        assert exc.value.code == "external_service_error"

    for incomplete in ({"description": "D"}, {"title": "T"}, {"title": "  ", "description": "D"}):
        with pytest.raises(ExternalServiceError):
            ai_service.normalize_quest_suggestion(incomplete)


# ---- 3. 失败口径 ---------------------------------------------------------


async def test_brief_success_returns_five_fields(monkeypatch):
    fake = FakeQuestClient()
    _patch_llm(monkeypatch, fake)

    out = await ai_service.generate_quest_from_brief(
        brief="口算 4 页,100 以内", child_level=2, narrative_context="霜原赛季",
    )

    assert fake.calls == 1
    assert set(out) == {"title", "description", "xp_reward", "difficulty", "time_deposit"}
    assert out["difficulty"] == 3 and out["time_deposit"] == 12
    # 两个新数值字段在模型提示里被列为必需(稳定输出)
    assert "difficulty" in fake.json_schemas[0]["required"]
    assert "time_deposit" in fake.json_schemas[0]["required"]


async def test_brief_keeps_503_when_llm_not_configured(monkeypatch):
    """能力未启用/未配置:保持 503 service_unavailable,不翻译成 502。"""
    def _raise():
        raise ServiceUnavailableError("AI「llm」能力未配置")

    monkeypatch.setattr(ai_service, "get_llm_client", _raise)

    with pytest.raises(ServiceUnavailableError) as exc:
        await ai_service.generate_quest_from_brief(brief="打扫房间")
    assert exc.value.http_status == 503
    assert exc.value.code == "service_unavailable"


async def test_brief_timeout_is_explicit_502(monkeypatch):
    fake = FakeQuestClient(delay=1.0)
    _patch_llm(monkeypatch, fake)

    with pytest.raises(ExternalServiceError) as exc:
        await ai_service.generate_quest_from_brief(brief="打扫房间", timeout_seconds=0.01)
    assert exc.value.http_status == 502
    assert "超时" in exc.value.message


async def test_brief_invalid_json_is_explicit_502(monkeypatch):
    """网关返回非 JSON:chat_json 抛 JSONDecodeError -> 502,不是裸 500。"""
    import json

    fake = FakeQuestClient(error=json.JSONDecodeError("bad", "{", 0))
    _patch_llm(monkeypatch, fake)

    with pytest.raises(ExternalServiceError) as exc:
        await ai_service.generate_quest_from_brief(brief="打扫房间")
    assert exc.value.http_status == 502
    assert exc.value.code == "external_service_error"


async def test_brief_non_dict_payload_is_explicit_502(monkeypatch):
    fake = FakeQuestClient(data=["not-a-dict"])
    _patch_llm(monkeypatch, fake)

    with pytest.raises(ExternalServiceError):
        await ai_service.generate_quest_from_brief(brief="打扫房间")


async def test_brief_passes_through_external_service_error(monkeypatch):
    """底层已抛 external_service_error(HTTP 错误)时不二次包装。"""
    original = ExternalServiceError("LLM 调用失败: 502")
    fake = FakeQuestClient(error=original)
    _patch_llm(monkeypatch, fake)

    with pytest.raises(ExternalServiceError) as exc:
        await ai_service.generate_quest_from_brief(brief="打扫房间")
    assert exc.value is original


async def test_generate_quest_legacy_path_unchanged(monkeypatch):
    """老接口仍原样透传 LLM 输出(含新增字段),不做收敛。"""
    fake = FakeQuestClient()
    _patch_llm(monkeypatch, fake)

    out = await ai_service.generate_quest(topic="打扫房间", child_level=1, narrative_context="")
    assert out["title"] == "晨光中的委托"
    assert out["lore_snippet"]  # 老字段仍在
    assert fake.json_schemas[0]["required"] == ai_service.QUEST_JSON_SCHEMA["required"]


# ---- 4. 路由契约(不依赖数据库) -----------------------------------------


def test_route_is_registered_and_parents_only():
    from app.api.v1.tasks import brief_router

    paths = {(r.path, tuple(sorted(r.methods))) for r in brief_router.routes}
    assert ("/scn/tasks/generate-from-brief", ("POST",)) in paths
    # 父母专属:handler 的依赖里有角色守卫
    route = next(r for r in brief_router.routes if r.path.endswith("generate-from-brief"))
    dep_names = {getattr(d.call, "__name__", "") for d in route.dependant.dependencies}
    assert "_checker" in dep_names, f"缺角色守卫: {dep_names}"


async def test_route_requires_auth(api_client: AsyncClient):
    """缺 Authorization 头 -> 401,不落到 LLM 或数据库。"""
    resp = await api_client.post(
        "/api/v1/scn/tasks/generate-from-brief", json={"brief": "打扫房间"},
    )
    assert resp.status_code == 401
    assert resp.json()["data"]["error_code"] == "unauthorized"

    resp = await api_client.post(
        "/api/v1/scn/tasks/generate-from-brief",
        json={"brief": "打扫房间"},
        headers={"Authorization": "Bearer not-a-jwt"},
    )
    assert resp.status_code == 401


async def test_handler_projects_llm_output_to_suggestion(monkeypatch):
    """直接调用 handler(绕开 FastAPI/DB):出参是 5 字段建议,且不写库。"""
    from app.api.v1 import tasks

    fake = FakeQuestClient()
    _patch_llm(monkeypatch, fake)

    async def _context(db, *, family_id, season_id):
        return "霜原赛季的剧情"

    async def _cap(db, *, family_id, target_date):
        return 50

    monkeypatch.setattr(tasks, "_brief_narrative_context", _context)
    monkeypatch.setattr(tasks, "_brief_deposit_cap", _cap)

    resp = await tasks.generate_from_brief(
        TaskBriefGenerateRequest(brief="口算 4 页", child_level=2),
        db=None,
        user=SimpleNamespace(family_id="fam-1"),
    )

    assert isinstance(resp, ApiResponse)
    assert isinstance(resp.data, TaskBriefSuggestion)
    assert resp.data.title == "晨光中的委托"
    assert resp.data.difficulty == 3
    assert resp.data.time_deposit == 12


async def test_handler_rejects_out_of_range_target_date(monkeypatch):
    from app.api.v1 import tasks
    from app.common.exceptions import ValidationError

    fake = FakeQuestClient()
    _patch_llm(monkeypatch, fake)

    today = today_bj()
    for bad in (today - timedelta(days=1), today + timedelta(days=31)):
        with pytest.raises(ValidationError) as exc:
            await tasks.generate_from_brief(
                TaskBriefGenerateRequest(brief="打扫房间", target_date=bad),
                db=None, user=SimpleNamespace(family_id="fam-1"),
            )
        assert exc.value.http_status == 422
    assert fake.calls == 0  # 校验不过就不该打 LLM


# ---- 5. 需要数据库的端到端用例(库不可达时按 db_ready 跳过) --------------


@pytest.mark.db
async def test_api_generate_from_brief_end_to_end(
    api_client: AsyncClient, db_session, seeded_family: SeededFamily, monkeypatch,
):
    """激活赛季提供叙事背景;建议按当日配额封顶;**不入库**。"""
    from sqlalchemy import func, select

    from app.models.scn_task_instance import ScnTaskInstance
    from app.models.scn_task_template import ScnTaskTemplate

    family_id = seeded_family.family.id  # 开发库是共享的,计数必须按家庭收窄

    async def _instances() -> int:
        return await db_session.scalar(
            select(func.count()).select_from(ScnTaskInstance)
            .where(ScnTaskInstance.family_id == family_id)
        )

    async def _templates() -> int:
        return await db_session.scalar(
            select(func.count()).select_from(ScnTaskTemplate)
            .where(ScnTaskTemplate.family_id == family_id)
        )

    before = (await _instances(), await _templates())

    fake = FakeQuestClient(data={
        "title": "晨光中的委托", "description": "把口算 4 页做完",
        "lore_snippet": "lore", "xp_reward": 120, "type": "DAILY",
        "difficulty": 4, "time_deposit": 999,  # 会被当日配额封顶
    })
    _patch_llm(monkeypatch, fake)

    resp = await api_client.post(
        "/api/v1/scn/tasks/generate-from-brief",
        json={"brief": "口算 4 页,100 以内", "child_level": 2},
        headers=_auth_headers(seeded_family.parent),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert set(data) == {"title", "description", "xp_reward", "difficulty", "time_deposit"}
    assert data["difficulty"] == 4
    assert data["time_deposit"] < 999  # 已被当日配额封顶
    assert fake.calls == 1

    assert (await _instances(), await _templates()) == before  # 不入库


@pytest.mark.db
async def test_api_generate_from_brief_child_forbidden(
    api_client: AsyncClient, seeded_family: SeededFamily,
):
    resp = await api_client.post(
        "/api/v1/scn/tasks/generate-from-brief",
        json={"brief": "打扫房间"},
        headers=_auth_headers(seeded_family.child_account),
    )
    assert resp.status_code == 403
    assert resp.json()["data"]["error_code"] == "permission_denied"


@pytest.mark.db
async def test_api_generate_from_brief_returns_503_when_llm_unconfigured(
    api_client: AsyncClient, seeded_family: SeededFamily, monkeypatch,
):
    from app.common.llm.factory import get_llm_client

    get_llm_client.cache_clear()
    monkeypatch.setattr(settings.ai.llm, "base_url", "")
    monkeypatch.setattr(settings.ai.llm, "api_key", "")
    monkeypatch.setattr(settings.ai.llm, "model", "")
    try:
        resp = await api_client.post(
            "/api/v1/scn/tasks/generate-from-brief",
            json={"brief": "打扫房间"},
            headers=_auth_headers(seeded_family.parent),
        )
        assert resp.status_code == 503
        assert resp.json()["data"]["error_code"] == "service_unavailable"
    finally:
        get_llm_client.cache_clear()


@pytest.mark.db
async def test_api_generate_from_brief_validates_request(
    api_client: AsyncClient, seeded_family: SeededFamily,
):
    headers = _auth_headers(seeded_family.parent)
    base = "/api/v1/scn/tasks/generate-from-brief"

    # 空 brief / 多传字段 / 日期格式非法 / 日期越界:一律 422
    for payload in (
        {"brief": ""},
        {"brief": "打扫房间", "unexpected": 1},
        {"brief": "打扫房间", "target_date": "not-a-date"},
        {"brief": "打扫房间", "target_date": str(today_bj() - timedelta(days=1))},
        {"brief": "打扫房间", "target_date": str(today_bj() + timedelta(days=31))},
    ):
        resp = await api_client.post(base, json=payload, headers=headers)
        assert resp.status_code == 422, (payload, resp.text)