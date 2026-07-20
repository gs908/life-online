"""动态主题服务。"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exceptions import NotFoundError, PermissionDeniedError
from app.common.llm import LLMMessage, get_llm_client
from app.models.theme_style import ThemeStyle


DEFAULT_THEME_TOKENS: dict[str, Any] = {
    "palette": {
        "primary": "#7C3AED",
        "secondary": "#F59E0B",
        "background": "#111827",
        "surface": "#1F2937",
        "text": "#F9FAFB",
    },
    "mood": "adventure",
    "radius": "16px",
}


DEFAULT_THEME_CSS_VARS: dict[str, str] = {
    "--color-primary": "#7C3AED",
    "--color-secondary": "#F59E0B",
    "--color-background": "#111827",
    "--color-surface": "#1F2937",
    "--color-text": "#F9FAFB",
    "--radius-card": "16px",
}


THEME_SYSTEM_PROMPT = """
你是一个儿童家庭任务 RPG 产品的视觉主题设计师。根据用户给定的场景,生成可落地的主题样式。
要求:
- 适合儿童和家庭场景,积极、安全、易读
- 输出必须是合法 JSON
- css_vars 的 key 必须是 CSS 变量名,例如 --color-primary
""".strip()


THEME_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "description": {"type": "string"},
        "tokens": {"type": "object"},
        "css_vars": {"type": "object"},
    },
    "required": ["name", "description", "tokens", "css_vars"],
}


async def list_themes(db: AsyncSession, *, family_id: str) -> list[ThemeStyle]:
    result = await db.execute(
        select(ThemeStyle)
        .where((ThemeStyle.family_id == family_id) | (ThemeStyle.is_system.is_(True)))
        .order_by(ThemeStyle.is_system.desc(), ThemeStyle.created_at.desc())
    )
    return list(result.scalars().all())


async def get_theme(db: AsyncSession, *, theme_id: str, family_id: str) -> ThemeStyle:
    theme = await db.get(ThemeStyle, theme_id)
    if not theme:
        raise NotFoundError(f"主题 {theme_id} 不存在")
    if not theme.is_system and theme.family_id != family_id:
        raise PermissionDeniedError("只能访问自己家庭的主题")
    return theme


async def create_theme(
    db: AsyncSession,
    *,
    family_id: str,
    name: str,
    scene_prompt: str = "",
    description: str = "",
    tokens: dict[str, Any] | None = None,
    css_vars: dict[str, str] | None = None,
    is_active: bool = False,
) -> ThemeStyle:
    if is_active:
        await _deactivate_family_themes(db, family_id)
    theme = ThemeStyle(
        family_id=family_id,
        name=name,
        scene_prompt=scene_prompt,
        description=description,
        tokens=tokens or DEFAULT_THEME_TOKENS,
        css_vars=css_vars or DEFAULT_THEME_CSS_VARS,
        is_system=False,
        is_active=is_active,
    )
    db.add(theme)
    await db.commit()
    await db.refresh(theme)
    return theme


async def update_theme(
    db: AsyncSession,
    *,
    theme_id: str,
    family_id: str,
    **patch,
) -> ThemeStyle:
    theme = await get_theme(db, theme_id=theme_id, family_id=family_id)
    if theme.is_system:
        raise PermissionDeniedError("系统主题不可编辑")
    if patch.get("is_active") is True:
        await _deactivate_family_themes(db, family_id)
    for key, value in patch.items():
        if value is not None:
            setattr(theme, key, value)
    await db.commit()
    await db.refresh(theme)
    return theme


async def delete_theme(db: AsyncSession, *, theme_id: str, family_id: str) -> None:
    theme = await get_theme(db, theme_id=theme_id, family_id=family_id)
    if theme.is_system:
        raise PermissionDeniedError("系统主题不可删除")
    await db.delete(theme)
    await db.commit()


async def activate_theme(db: AsyncSession, *, theme_id: str, family_id: str) -> ThemeStyle:
    return await update_theme(db, theme_id=theme_id, family_id=family_id, is_active=True)


async def generate_theme(
    db: AsyncSession,
    *,
    family_id: str,
    scene_prompt: str,
    name: str | None = None,
    activate: bool = False,
) -> ThemeStyle:
    client = get_llm_client()
    resp = await client.chat_json(
        messages=[
            LLMMessage(role="system", content=THEME_SYSTEM_PROMPT),
            LLMMessage(role="user", content=f"场景:{scene_prompt}\n请生成主题 JSON。"),
        ],
        json_schema=THEME_JSON_SCHEMA,
    )
    data = resp.data
    if isinstance(data, str):
        data = json.loads(data)
    return await create_theme(
        db,
        family_id=family_id,
        name=name or data.get("name") or "自定义主题",
        scene_prompt=scene_prompt,
        description=data.get("description", ""),
        tokens=data.get("tokens") or DEFAULT_THEME_TOKENS,
        css_vars=data.get("css_vars") or DEFAULT_THEME_CSS_VARS,
        is_active=activate,
    )


async def _deactivate_family_themes(db: AsyncSession, family_id: str) -> None:
    await db.execute(
        update(ThemeStyle)
        .where(ThemeStyle.family_id == family_id, ThemeStyle.is_active.is_(True))
        .values(is_active=False)
    )
