"""AI 服务:基于 LLM 客户端封装业务层调用。

业务层只 import 此模块,不直接接触 common.llm。
"""
from __future__ import annotations

from app.common.llm import LLMMessage, get_llm_client


QUEST_SYSTEM_PROMPT = """
你是一个面向家庭任务游戏化产品的"地下城主",负责把现实任务包装成中世纪/奇幻 RPG 风格的冒险任务。
要求:
- 严格根据用户的当前主题/赛季剧情包装,所有 lore 必须贴合主题
- 描述必须具体可执行,孩子能照着做
- XP 范围 50-500,难度匹配孩子等级
- 输出必须是合法 JSON,字段齐全
""".strip()


QUEST_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "description": {"type": "string"},
        "lore_snippet": {"type": "string"},
        "xp_reward": {"type": "integer"},
        "type": {"type": "string", "enum": ["DAILY", "CHALLENGE", "CHAIN", "TIMED", "COOP"]},
        "reminder_message": {"type": "string"},
    },
    "required": ["title", "description", "lore_snippet", "xp_reward", "type"],
}


async def generate_quest(
    *, topic: str, child_level: int, narrative_context: str,
) -> dict:
    """根据现实任务主题,生成 RPG 包装的 quest 内容。"""
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
        json_schema=QUEST_JSON_SCHEMA,
    )
    return resp.data


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
