"""任务内容生成测试(docs/15 §11,DEV-49)。

覆盖 T1-T8:
- T1 content_mode=STATIC:实例保留模板 lore_snippet,content_source=TEMPLATE,LLM 未被调用;
- T2 content_mode=LLM 正常返回:lore_snippet 保存叙事,content_source=LLM,
  title/description/xp_reward/time_deposit 与模板一致;
- T3 LLM 报错:实例仍创建、叙事回落模板文本、content_source=FALLBACK、
  不向外抛异常、统计 fallback=1;
- T4 返回文本超长:结果为 FALLBACK;
- T5 同日运行批量作业两次:仅 1 条实例,LLM 仅调用 1 次;
- T6 roll_forward 路径:LLM 未被调用,叙事不变;
- T7 LLM 能力关闭(task_content.llm_enabled=false):全部实例仍创建,
  content_source=FALLBACK,作业不失败,LLM 未被调用;
- T8 迁移可升级可回滚,存量行取得默认值。

LLM 一律用假客户端(统计调用次数),不触网。需要可连接的数据库
(远程优先),不可达时自动跳过。
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import date, datetime, time, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.llm.types import LLMJsonResponse
from app.common.timeutil import BJ_TZ
from app.config import settings
from app.dev.seed import SeededFamily, cleanup_family, seed_basic_family
from app.models.enums import ContentMode, ContentSource, TaskStatus, TriggerKind
from app.models.scn_task_instance import ScnTaskInstance
from app.models.scn_task_template import ScnTaskTemplate
from app.models.scn_task_template_trigger import ScnTaskTemplateTrigger
from app.services import ai_service, task_generator_service

pytestmark = pytest.mark.db

TODAY = date(2026, 10, 18)
YESTERDAY = TODAY - timedelta(days=1)
NOW = datetime(2026, 10, 18, 0, 10, tzinfo=BJ_TZ)  # 00:10 批量作业窗口

TEMPLATE_LORE = "模板原文叙事:老铁匠铺的炉火映红半条街。"
FAKE_NARRATIVE = "晨雾未散,酒馆门前的告示板钉着一张新委托,少年攥紧背带推门而出。"


class FakeNarrativeClient:
    """假 LLM 客户端:统计 chat_json 调用次数与请求参数,不触网。"""

    def __init__(
        self,
        *,
        narrative: str | None = FAKE_NARRATIVE,
        error: Exception | None = None,
    ) -> None:
        self.narrative = narrative
        self.error = error
        self.calls = 0
        self.temperatures: list[float | None] = []

    async def chat_json(self, messages, json_schema=None, *, temperature=None):
        self.calls += 1
        self.temperatures.append(temperature)
        if self.error is not None:
            raise self.error
        return LLMJsonResponse(
            data={"narrative": self.narrative},
            raw={"usage": {"total_tokens": 42}},
        )


def _patch_llm(monkeypatch, fake: FakeNarrativeClient) -> None:
    """R15:生成器只经 ai_service 取客户端;测试在 ai_service 层注入假实现。"""
    monkeypatch.setattr(ai_service, "get_llm_client", lambda: fake)


async def _make_template(
    db: AsyncSession, seeded: SeededFamily, *, triggers: list, **kw,
) -> ScnTaskTemplate:
    template = ScnTaskTemplate(
        family_id=seeded.family.id,
        season_id=seeded.season.id,
        creator_account_id=seeded.parent.id,
        title=kw.pop("title", "内容生成测试任务"),
        lore_snippet=kw.pop("lore_snippet", TEMPLATE_LORE),
        **kw,
    )
    template.triggers = triggers
    db.add(template)
    await db.commit()
    return template


def _trigger(kind: TriggerKind, **kw) -> ScnTaskTemplateTrigger:
    return ScnTaskTemplateTrigger(kind=kind, generate_at=kw.pop("generate_at", time(0, 0)), **kw)


async def _make_instance(
    db: AsyncSession, template: ScnTaskTemplate, *, day: date | None,
    status: TaskStatus = TaskStatus.AVAILABLE,
) -> ScnTaskInstance:
    instance = ScnTaskInstance(
        family_id=template.family_id,
        season_id=template.season_id,
        template_id=template.id,
        title=template.title,
        lore_snippet=template.lore_snippet,
        xp_reward=template.xp_reward,
        status=status,
        generated_for_date=day,
        time_deposit=template.time_deposit,
    )
    db.add(instance)
    await db.commit()
    return instance


async def _count_instances(db: AsyncSession, template_id: str) -> int:
    rows = (
        await db.execute(
            select(ScnTaskInstance).where(ScnTaskInstance.template_id == template_id)
        )
    ).scalars().all()
    return len(rows)


@pytest_asyncio.fixture
async def seeded(db_session: AsyncSession) -> SeededFamily:
    seeded = await seed_basic_family(db_session, suffix="content")
    family_id = seeded.family.id  # 兜底 rollback 会 expire 对象,先取普通值
    try:
        yield seeded
    finally:
        await cleanup_family(db_session, family_id)


# ---- T1:STATIC 模式 —— 复制模板文本,不调 LLM ----


async def test_t1_static_mode_copies_template_without_llm(db_session, seeded, monkeypatch):
    fake = FakeNarrativeClient()
    _patch_llm(monkeypatch, fake)
    template = await _make_template(
        db_session, seeded, triggers=[_trigger(TriggerKind.DAILY)],
        content_mode=ContentMode.STATIC,
    )

    instance, action = await task_generator_service.generate_for_template(
        db_session, template, today=TODAY, now=NOW,
    )

    assert action == "created"
    assert instance.lore_snippet == TEMPLATE_LORE  # 实例保留模板文本
    assert instance.content_source == ContentSource.TEMPLATE
    assert instance.generation_meta is None
    assert fake.calls == 0  # LLM 未被调用


# ---- T2:LLM 模式正常返回 —— 叙事落 lore_snippet,任务实质不变 ----


async def test_t2_llm_success_saves_narrative(db_session, seeded, monkeypatch):
    fake = FakeNarrativeClient()
    _patch_llm(monkeypatch, fake)
    template = await _make_template(
        db_session, seeded, triggers=[_trigger(TriggerKind.DAILY)],
        content_mode=ContentMode.LLM,
        description="口算 4 页,100 以内",
    )

    instance, action = await task_generator_service.generate_for_template(
        db_session, template, today=TODAY, now=NOW,
    )

    assert action == "created"
    assert fake.calls == 1
    assert fake.temperatures == [0.8]  # R16
    assert instance.lore_snippet == FAKE_NARRATIVE
    assert instance.content_source == ContentSource.LLM
    # R9:任务实质保持模板原文
    assert instance.title == template.title
    assert instance.description == template.description
    assert instance.xp_reward == template.xp_reward
    assert instance.time_deposit == template.time_deposit
    # R14:generation_meta 含模型名/提示词哈希/token 数/耗时
    meta = instance.generation_meta
    assert meta["model"] == settings.ai.llm.model
    assert meta["prompt_hash"]
    assert meta["tokens"] == 42
    assert isinstance(meta["elapsed_ms"], int)
    assert "error" not in meta


# ---- T3:LLM 报错 —— 实例仍创建,回落模板文本,不外抛 ----


async def test_t3_llm_error_falls_back_and_still_creates(db_session, seeded, monkeypatch):
    from app.common.exceptions import ExternalServiceError

    fake = FakeNarrativeClient(error=ExternalServiceError("LLM 调用失败"))
    _patch_llm(monkeypatch, fake)
    template = await _make_template(
        db_session, seeded, triggers=[_trigger(TriggerKind.DAILY)],
        content_mode=ContentMode.LLM,
    )

    # 不向外抛异常(R13)
    instance, action = await task_generator_service.generate_for_template(
        db_session, template, today=TODAY, now=NOW,
    )

    assert action == "created"  # 实例创建始终成功
    assert fake.calls == 1
    assert instance.lore_snippet == TEMPLATE_LORE  # 回落模板文本
    assert instance.content_source == ContentSource.FALLBACK
    assert instance.generation_meta["error"] == "ExternalServiceError"

    stats = await task_generator_service.run_generation(db_session, today=TODAY, now=NOW)
    # 上一步已创建,本轮 exists;fallback 计数口径:本轮无新建,FALLBACK 实例不再重复计数
    assert stats["exists"] == 1 and stats["fallback"] == 0


async def test_t3_fallback_counted_in_run_generation(db_session, seeded, monkeypatch):
    from app.common.exceptions import ExternalServiceError

    fake = FakeNarrativeClient(error=ExternalServiceError("LLM 调用失败"))
    _patch_llm(monkeypatch, fake)
    await _make_template(
        db_session, seeded, triggers=[_trigger(TriggerKind.DAILY)],
        content_mode=ContentMode.LLM,
    )

    stats = await task_generator_service.run_generation(db_session, today=TODAY, now=NOW)
    assert stats["created"] == 1
    assert stats["fallback"] == 1  # T3:统计中 fallback=1
    assert stats["llm_generated"] == 0
    assert stats["errors"] == 0


# ---- 🟡硬化路径:上下文加载失败 / 返回结构非法 —— 仍回落,实例照建 ----


async def test_context_load_failure_falls_back(db_session, seeded, monkeypatch):
    """🟡1:赛季/孩子上下文加载抛异常时,实例仍创建、回落模板文本(R13)。"""
    fake = FakeNarrativeClient()
    _patch_llm(monkeypatch, fake)

    async def _boom(db, template):
        raise RuntimeError("context load failed")

    monkeypatch.setattr(task_generator_service, "_load_content_context", _boom)
    template = await _make_template(
        db_session, seeded, triggers=[_trigger(TriggerKind.DAILY)],
        content_mode=ContentMode.LLM,
    )

    instance, action = await task_generator_service.generate_for_template(
        db_session, template, today=TODAY, now=NOW,
    )

    assert action == "created"  # 实例创建始终成功
    assert fake.calls == 0
    assert instance.lore_snippet == TEMPLATE_LORE
    assert instance.content_source == ContentSource.FALLBACK
    assert instance.generation_meta["error"] == "RuntimeError"


async def test_invalid_payload_falls_back_with_full_meta(db_session, seeded, monkeypatch):
    """🟡2:chat_json 返回非 dict JSON 时,回落 FALLBACK 且 generation_meta 保真。"""

    class _BadShapeClient(FakeNarrativeClient):
        async def chat_json(self, messages, json_schema=None, *, temperature=None):
            self.calls += 1
            self.temperatures.append(temperature)
            return SimpleNamespace(data=["not-a-dict"], raw={"usage": {"total_tokens": 7}})

    fake = _BadShapeClient()
    _patch_llm(monkeypatch, fake)
    template = await _make_template(
        db_session, seeded, triggers=[_trigger(TriggerKind.DAILY)],
        content_mode=ContentMode.LLM,
    )

    instance, action = await task_generator_service.generate_for_template(
        db_session, template, today=TODAY, now=NOW,
    )

    assert action == "created"
    assert fake.calls == 1
    assert instance.lore_snippet == TEMPLATE_LORE
    assert instance.content_source == ContentSource.FALLBACK
    meta = instance.generation_meta
    assert meta["error"] == "InvalidPayload"
    assert meta["model"] == settings.ai.llm.model
    assert meta["prompt_hash"]
    assert meta["tokens"] == 7  # 解析失败不丢已采集字段
    assert isinstance(meta["elapsed_ms"], int)


# ---- T4:返回文本超长 —— 按失败处理(R23) ----


async def test_t4_overlong_narrative_falls_back(db_session, seeded, monkeypatch):
    fake = FakeNarrativeClient(narrative="长" * (settings.task_content.max_narrative_chars + 1))
    _patch_llm(monkeypatch, fake)
    template = await _make_template(
        db_session, seeded, triggers=[_trigger(TriggerKind.DAILY)],
        content_mode=ContentMode.LLM,
    )

    instance, action = await task_generator_service.generate_for_template(
        db_session, template, today=TODAY, now=NOW,
    )

    assert action == "created"
    assert fake.calls == 1
    assert instance.lore_snippet == TEMPLATE_LORE
    assert instance.content_source == ContentSource.FALLBACK
    assert instance.generation_meta["error"] == "NarrativeTooLong"


# ---- T5:同日两次批量作业 —— 1 条实例,LLM 仅 1 次 ----


async def test_t5_double_run_single_instance_single_llm_call(db_session, seeded, monkeypatch):
    fake = FakeNarrativeClient()
    _patch_llm(monkeypatch, fake)
    template = await _make_template(
        db_session, seeded, triggers=[_trigger(TriggerKind.DAILY)],
        content_mode=ContentMode.LLM,
    )

    first = await task_generator_service.run_generation(db_session, today=TODAY, now=NOW)
    second = await task_generator_service.run_generation(db_session, today=TODAY, now=NOW)

    assert first["created"] == 1 and first["llm_generated"] == 1
    assert second["created"] == 0 and second["exists"] == 1
    assert await _count_instances(db_session, template.id) == 1
    assert fake.calls == 1  # LLM 仅 1 次(R11:exists 不重调)


# ---- T6:roll_forward —— 不调 LLM,叙事不变 ----


async def test_t6_roll_forward_skips_llm_keeps_narrative(db_session, seeded, monkeypatch):
    fake = FakeNarrativeClient()
    _patch_llm(monkeypatch, fake)
    template = await _make_template(
        db_session, seeded, triggers=[_trigger(TriggerKind.DAILY)],
        content_mode=ContentMode.LLM,
    )
    old = await _make_instance(db_session, template, day=YESTERDAY)
    old.lore_snippet = "首次生成的叙事"
    await db_session.commit()

    rolled, action = await task_generator_service.generate_for_template(
        db_session, template, today=TODAY, now=NOW,
    )

    assert action == "rolled_forward"
    assert rolled.id == old.id
    assert rolled.lore_snippet == "首次生成的叙事"  # 顺延保留首次生成的叙事
    assert fake.calls == 0  # R11:roll_forward 不调 LLM


# ---- T7:能力关闭 —— 全量 FALLBACK,作业不失败,不调 LLM ----


async def test_t7_llm_disabled_all_fallback(db_session, seeded, monkeypatch):
    fake = FakeNarrativeClient()
    _patch_llm(monkeypatch, fake)
    monkeypatch.setattr(settings.task_content, "llm_enabled", False)
    llm_template = await _make_template(
        db_session, seeded, triggers=[_trigger(TriggerKind.DAILY)],
        content_mode=ContentMode.LLM,
    )
    static_template = await _make_template(
        db_session, seeded, triggers=[_trigger(TriggerKind.DAILY)],
        content_mode=ContentMode.STATIC,
    )

    stats = await task_generator_service.run_generation(db_session, today=TODAY, now=NOW)

    assert stats["errors"] == 0  # 作业不失败
    assert stats["created"] == 2
    assert stats["fallback"] == 1 and stats["llm_generated"] == 0
    assert fake.calls == 0  # R21:能力关闭不调 LLM
    rows = (
        await db_session.execute(
            select(ScnTaskInstance).where(
                ScnTaskInstance.template_id.in_([llm_template.id, static_template.id])
            )
        )
    ).scalars().all()
    by_template = {r.template_id: r for r in rows}
    llm_row = by_template[llm_template.id]
    static_row = by_template[static_template.id]
    # LLM 模板:运维可看出"模板要求的是 LLM"
    assert llm_row.content_source == ContentSource.FALLBACK
    assert llm_row.lore_snippet == TEMPLATE_LORE
    assert llm_row.generation_meta["error"] == "LLMDisabled"
    # STATIC 模板不受影响
    assert static_row.content_source == ContentSource.TEMPLATE


# ---- T8:迁移可升级可回滚,存量行取默认值 ----


def _run_alembic(target: str) -> None:
    from alembic.config import Config

    from alembic import command

    server_root = Path(__file__).resolve().parents[1]
    cfg = Config(str(server_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(server_root / "alembic"))
    command.upgrade(cfg, target)


def _alembic_downgrade_one() -> None:
    """回滚一版:显式定位 head 的 down_revision(不依赖相对目标 "-1" 解析)。"""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    from alembic import command

    server_root = Path(__file__).resolve().parents[1]
    cfg = Config(str(server_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(server_root / "alembic"))
    script = ScriptDirectory.from_config(cfg)
    head = script.get_current_head()
    target = script.get_revision(head).down_revision
    command.downgrade(cfg, target)


def _column_exists(table: str, column: str) -> bool:
    from sqlalchemy import create_engine

    from app.config import settings as app_settings

    engine = create_engine(app_settings.database.url_sync)
    try:
        with engine.connect() as conn:
            return conn.execute(
                text(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name = :t AND column_name = :c"
                ),
                {"t": table, "c": column},
            ).scalar() == 1
    finally:
        engine.dispose()


async def test_t8_migration_upgrade_downgrade_with_defaults(db_session, seeded):
    """T8:upgrade 增列、存量行经 server_default 取默认值、downgrade 可回滚。"""
    await asyncio.to_thread(_run_alembic, "head")
    assert _column_exists("scn_task_template", "content_mode")
    assert _column_exists("scn_task_template", "content_brief")
    assert _column_exists("scn_task_instance", "content_source")
    assert _column_exists("scn_task_instance", "generation_meta")

    # 存量行口径:裸 SQL 插入不带新列,读回 server_default 值。
    tpl_id, ins_id = str(uuid.uuid4()), str(uuid.uuid4())
    await db_session.execute(
        text(
            "INSERT INTO scn_task_template "
            "(id, family_id, season_id, title, description, xp_reward, type, "
            " reminder_minutes_before, time_deposit, is_active) "
            "VALUES (:id, :fid, :sid, 'T8 迁移默认值', '', 50, 'DAILY', 15, 10, true)"
        ),
        {"id": tpl_id, "fid": seeded.family.id, "sid": seeded.season.id},
    )
    await db_session.execute(
        text(
            "INSERT INTO scn_task_instance "
            "(id, family_id, season_id, template_id, title, description, xp_reward, "
            " status, time_deposit, coin_delta, abandon_count_at_submit) "
            "VALUES (:id, :fid, :sid, :tid, 'T8 实例', '', 50, 'AVAILABLE', 10, 0, 0)"
        ),
        {"id": ins_id, "fid": seeded.family.id, "sid": seeded.season.id, "tid": tpl_id},
    )
    await db_session.commit()
    tpl_mode = await db_session.scalar(
        text("SELECT content_mode FROM scn_task_template WHERE id = :id"), {"id": tpl_id},
    )
    ins_source = await db_session.scalar(
        text("SELECT content_source FROM scn_task_instance WHERE id = :id"), {"id": ins_id},
    )
    assert tpl_mode == "STATIC"  # R1:存量行取默认值
    assert ins_source == "TEMPLATE"  # R3:存量行取默认值

    # 释放会话上的隐式事务/表锁,避免阻塞迁移连接的 DDL。
    await db_session.rollback()
    try:
        await asyncio.to_thread(_alembic_downgrade_one)  # downgrade:回滚一版
        assert not _column_exists("scn_task_template", "content_mode")
        assert not _column_exists("scn_task_instance", "content_source")
    finally:
        # 无论中途成败,恢复到 head(新模型代码依赖这些列)。
        await db_session.rollback()
        await asyncio.to_thread(_run_alembic, "head")
    assert _column_exists("scn_task_template", "content_mode")
    assert _column_exists("scn_task_instance", "content_source")
