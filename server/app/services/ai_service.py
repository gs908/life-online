"""AI 服务:基于 LLM 客户端封装业务层调用。

业务层只 import 此模块,不直接接触 common.llm。
"""
from __future__ import annotations

import asyncio
import hashlib
import time

from app.common.exceptions import ExternalServiceError, ServiceUnavailableError
from app.common.llm import LLMMessage, get_llm_client
from app.config import settings

QUEST_SYSTEM_PROMPT = """
你是一个面向家庭任务游戏化产品的"地下城主",负责把现实任务包装成中世纪/奇幻 RPG 风格的冒险任务。
要求:
- 严格根据用户的当前主题/赛季剧情包装,所有 lore 必须贴合主题
- 描述必须具体可执行,孩子能照着做
- XP 范围 50-500,难度匹配孩子等级
- difficulty 是 1-5 的整数(1 最易、5 最难),按任务的实际强度建议
- time_deposit 是孩子接取任务时冻结的时间币押金,取 >= 0 的整数
- 输出必须是合法 JSON,字段齐全
""".strip()


# xp_reward 的建议缺省值:与 TaskTemplateCreate / 模板模型同源的平台默认值。
DEFAULT_QUEST_XP = 50

QUEST_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "description": {"type": "string"},
        "lore_snippet": {"type": "string"},
        "xp_reward": {"type": "integer"},
        "type": {"type": "string", "enum": ["DAILY", "CHALLENGE", "CHAIN", "TIMED", "COOP"]},
        "reminder_message": {"type": "string"},
        # DEV-60 加法扩展:任务建议需要的两个数值字段。既有调用方(旧 AI 生成器
        # UI)只读 title/description/lore_snippet/xp_reward/type 并忽略多出来的
        # 字段,故这里只增不改;`required` 保持原样,老接口契约不变。
        "difficulty": {"type": "integer", "minimum": 1, "maximum": 5},
        "time_deposit": {"type": "integer", "minimum": 0},
    },
    "required": ["title", "description", "lore_snippet", "xp_reward", "type"],
}

# 「任务要点 → 任务建议」(DEV-60,docs/08 §6C)专用:在公共 schema 上把两个新
# 数值字段也列为必需,让模型稳定输出 —— 该接口的契约保证这 5 个字段齐全。
BRIEF_QUEST_JSON_SCHEMA = {
    **QUEST_JSON_SCHEMA,
    "required": [*QUEST_JSON_SCHEMA["required"], "difficulty", "time_deposit"],
}


async def _generate_quest_data(
    *, topic: str, child_level: int, narrative_context: str, json_schema: dict,
) -> dict:
    """调一次 LLM 产出 quest JSON(`generate_quest` 与 `generate_quest_from_brief` 共用)。"""
    client = get_llm_client()
    user_prompt = (
        f"现实任务:{topic}\n"
        f"孩子等级:{child_level}\n"
        f"当前赛季剧情:{narrative_context}\n"
        f"请输出 JSON。"
    )
    resp = await client.chat_json(
        messages=[
            LLMMessage(role="system", content=QUEST_SYSTEM_PROMPT),
            LLMMessage(role="user", content=user_prompt),
        ],
        json_schema=json_schema,
    )
    return resp.data


async def generate_quest(
    *, topic: str, child_level: int, narrative_context: str,
) -> dict:
    """根据现实任务主题,生成 RPG 包装的 quest 内容。

    行为与契约不变(DEV-60):schema 只是加法扩展,返回值仍原样透传 LLM 输出,
    字段补齐校验由前端做(`packages/admin/src/services/api/modules/ai.ts`)。
    """
    return await _generate_quest_data(
        topic=topic,
        child_level=child_level,
        narrative_context=narrative_context,
        json_schema=QUEST_JSON_SCHEMA,
    )


# ---- 任务要点 → 任务建议(DEV-60,docs/08 §6C)-----------------------------


def _coerce_int(value, *, default: int, minimum: int, maximum: int | None = None) -> int:
    """把 LLM 给的数值收敛到契约区间:缺失/非整数取 default,越界则 clamp。"""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    if number < minimum:
        return minimum
    if maximum is not None and number > maximum:
        return maximum
    return number


def normalize_quest_suggestion(data, *, deposit_cap: int | None = None) -> dict:
    """把 LLM 的 quest JSON 收敛成「任务建议」出参(docs/08 §6C)。

    出参恒为 5 个字段:title / description / xp_reward / difficulty /
    time_deposit。LLM 输出没有强 schema 约束,所以这里做**确定性收敛**而不是
    照抄,保证接口契约成立:

    - title / description 缺失或为空 -> 建议不可用,抛 502 `external_service_error`;
    - xp_reward 缺失 -> 平台默认 50(与模板默认值同源),越界 clamp 到 >= 0;
    - difficulty 缺失 -> 1,clamp 到 1-5(与 `xp_service` 的 clamp 口径一致);
    - time_deposit 缺失 -> 0,clamp 到 >= 0;给 `deposit_cap` 时再按当日配额封顶
      (与 `coin_service.deposit_cap`、docs/08 §6B 的 preview-deposit 同一口径)。

    这几个数字只是**渲染建议**,用户会在表单里确认或改写,所以缺字段取中性值
    比让整个预览失败更有用。
    """
    if not isinstance(data, dict):
        raise ExternalServiceError("AI 返回结构非法,请重试")
    title = str(data.get("title") or "").strip()
    description = str(data.get("description") or "").strip()
    if not title or not description:
        raise ExternalServiceError("AI 返回内容不完整,请重试")
    time_deposit = _coerce_int(data.get("time_deposit"), default=0, minimum=0)
    if deposit_cap is not None:
        time_deposit = min(time_deposit, max(0, deposit_cap))
    return {
        "title": title,
        "description": description,
        "xp_reward": _coerce_int(data.get("xp_reward"), default=DEFAULT_QUEST_XP, minimum=0),
        "difficulty": _coerce_int(data.get("difficulty"), default=1, minimum=1, maximum=5),
        "time_deposit": time_deposit,
    }


async def generate_quest_from_brief(
    *,
    brief: str,
    child_level: int = 1,
    narrative_context: str = "",
    deposit_cap: int | None = None,
    timeout_seconds: float = 15.0,
) -> dict:
    """「任务要点 → 任务建议」:复用 `generate_quest` 的提示词与 schema,只产出
    渲染建议,**不写库**(docs/08 §6C)。

    失败口径与批量叙事生成(docs/15 R12)对齐 —— 区别在于这里没有可回落的模板
    文本,所以不做降级,而是给出**明确**的错误:

    - 能力未启用 / 未配置 -> 原样 503 `service_unavailable`(沿用 DEV-9 降级约定,
      由 `require_ai_capability` 抛出,不在这里翻译);
    - 超时、HTTP 错误、非法 JSON、结构非法、核心字段缺失 -> 502
      `external_service_error`,前端提示"稍后重试"。
    """
    try:
        data = await asyncio.wait_for(
            _generate_quest_data(
                topic=brief,
                child_level=child_level,
                narrative_context=narrative_context,
                json_schema=BRIEF_QUEST_JSON_SCHEMA,
            ),
            timeout=timeout_seconds,
        )
    except ServiceUnavailableError:
        raise  # 能力未启用/未配置:保持 503,不误报成"调用失败"
    except TimeoutError as exc:
        raise ExternalServiceError(
            f"AI 生成超时(超过 {timeout_seconds:g} 秒),请稍后重试"
        ) from exc
    except ExternalServiceError:
        raise
    except Exception as exc:  # 非法 JSON / 结构异常统一成明确的 502
        raise ExternalServiceError(f"AI 生成失败: {exc}") from exc
    return normalize_quest_suggestion(data, deposit_cap=deposit_cap)


async def evaluate_proof(
    *, task_title: str, image_data_url: str,
) -> dict:
    """用 LLM 评判孩子提交的任务证明图片(纯文本评分,不传图也行)。

    当前实现走纯文本 LLM(OpenAI 协议不直接支持多模态),可后续切到多模态模型。
    """
    client = get_llm_client()
    schema = {
        "type": "object",
        "properties": {
            "rating": {"type": "integer", "minimum": 1, "maximum": 5},
            "comment": {"type": "string"},
        },
        "required": ["rating", "comment"],
    }
    resp = await client.chat_json(
        messages=[
            LLMMessage(
                role="system",
                content="你是一个温和的家长审核员,给孩子打分并写一句鼓励。",
            ),
            LLMMessage(
                role="user",
                content=f"任务:{task_title}\n(已收到任务证明图片)\n请给出 1-5 星评分与一句鼓励评语。",
            ),
        ],
        json_schema=schema,
    )
    return resp.data


# ---- 任务叙事生成(docs/15 §7,DEV-49)------------------------------------

TASK_NARRATIVE_SYSTEM_PROMPT = """
你为家庭任务游戏写一段简短的故事文本。
- 故事文本必须贴合当前赛季主题。
- 不要改变任务。不要增加工作量。不要减少工作量。
- 不要写数字、数量、页数、分钟数、奖励、难度。
- 不要写任务指令。
- 使用简体中文。
- 长度 40 到 120 字。
- 不要出现暴力、恐惧、恋爱、政治、宗教、医疗断言。
- 不要出现个人信息。不要出现孩子姓名。
- 主题为空时,写一段通用冒险场景。
""".strip()

TASK_NARRATIVE_JSON_SCHEMA = {
    "type": "object",
    "properties": {"narrative": {"type": "string"}},
    "required": ["narrative"],
}


class TaskNarrativeError(Exception):
    """任务叙事生成失败(docs/15 R12)。

    失败情形:能力未启用/未配置、HTTP 错误、超时、返回非法 JSON、
    返回空文本、文本超长。`meta` 携带 generation_meta 所需字段
    (模型名/提示词哈希/token 数/耗时毫秒/错误类名),调用方回落
    FALLBACK 时原样落库留档(docs/15 R14)。
    """

    def __init__(self, message: str, *, meta: dict) -> None:
        super().__init__(message)
        self.meta = meta


def _prompt_hash(system: str, user: str) -> str:
    """提示词指纹(sha256 前 16 位):generation_meta 留档用,不落提示词全文。"""
    return hashlib.sha256(f"{system}\x1f{user}".encode()).hexdigest()[:16]


async def generate_task_narrative(
    *,
    content_brief: str,
    topic: str,
    category: str | None = None,
    child_level: int = 1,
    is_weekend: bool = False,
    task_type: str | None = None,
    timeout_seconds: float = 15.0,
    max_narrative_chars: int = 200,
) -> tuple[str, dict]:
    """为任务实例生成一段叙事文本(docs/15 §7,R16-R19)。

    返回 (narrative, meta);meta 含模型名/提示词哈希/token 数/耗时(毫秒)。
    任何失败抛 TaskNarrativeError,meta 照常携带已采集字段与错误类名,
    由调用方(生成器)回落模板文本 —— 本函数只负责"调一次并校验结果",
    不做回落决策。

    - JSON schema: {"narrative": string},temperature 0.8(R16);
    - 超时作用于本次调用(wait_for 包裹,R22);
    - 空文本 / 超过 max_narrative_chars 均按失败处理(R12/R23)。
    """
    system = TASK_NARRATIVE_SYSTEM_PROMPT
    # R18:user 消息要素 = 任务要点、赛季主题、分类、孩子等级、日期类型、任务类型。
    user = (
        f"任务要点:{content_brief}\n"
        f"赛季主题:{topic.strip() if topic else '(空)'}\n"
        f"分类:{category or '未分类'}\n"
        f"孩子等级:{child_level}\n"
        f"日期类型:{'周末' if is_weekend else '工作日'}\n"
        f"任务类型:{task_type or 'DAILY'}\n"
        "请输出 JSON。"
    )
    meta: dict = {
        "model": settings.ai.llm.model,
        "prompt_hash": _prompt_hash(system, user),
        "tokens": None,
        "elapsed_ms": 0,
    }
    started = time.perf_counter()

    def _elapsed_ms() -> int:
        return int((time.perf_counter() - started) * 1000)

    try:
        client = get_llm_client()
        resp = await asyncio.wait_for(
            client.chat_json(
                messages=[
                    LLMMessage(role="system", content=system),
                    LLMMessage(role="user", content=user),
                ],
                json_schema=TASK_NARRATIVE_JSON_SCHEMA,
                temperature=0.8,
            ),
            timeout=timeout_seconds,
        )
        # 响应解析纳入同一 try(Mars 🟡2):网关忽略 response_format 返回非 dict
        # JSON 时,保真 generation_meta(模型名/提示词哈希/token/耗时)而非退化。
        meta["elapsed_ms"] = _elapsed_ms()
        usage = (resp.raw or {}).get("usage") or {}
        meta["tokens"] = usage.get("total_tokens")
        if not isinstance(resp.data, dict):
            meta["error"] = "InvalidPayload"
            raise TaskNarrativeError(
                f"任务叙事生成失败: 返回结构非法({type(resp.data).__name__})", meta=meta,
            )
        narrative = str(resp.data.get("narrative") or "").strip()
        if not narrative:
            meta["error"] = "EmptyNarrative"
            raise TaskNarrativeError("任务叙事生成失败: 返回空文本", meta=meta)
        if len(narrative) > max_narrative_chars:
            meta["error"] = "NarrativeTooLong"
            raise TaskNarrativeError(
                f"任务叙事生成失败: 文本超长({len(narrative)} > {max_narrative_chars})",
                meta=meta,
            )
    except TaskNarrativeError:
        raise  # 已带完整 meta,不二次包装
    except Exception as exc:
        meta["elapsed_ms"] = _elapsed_ms()
        meta.setdefault("error", type(exc).__name__)
        raise TaskNarrativeError(f"任务叙事生成失败: {exc}", meta=meta) from exc
    return narrative, meta
