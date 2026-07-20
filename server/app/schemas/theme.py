"""动态主题 DTO。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ThemeStyleCreate(BaseModel):
    name: str
    scene_prompt: str = ""
    description: str = ""
    tokens: dict[str, Any] = Field(default_factory=dict)
    css_vars: dict[str, str] = Field(default_factory=dict)
    is_active: bool = False


class ThemeStyleUpdate(BaseModel):
    name: str | None = None
    scene_prompt: str | None = None
    description: str | None = None
    tokens: dict[str, Any] | None = None
    css_vars: dict[str, str] | None = None
    is_active: bool | None = None


class ThemeGenerateRequest(BaseModel):
    scene_prompt: str
    name: str | None = None
    activate: bool = False


class ThemeStyleRead(BaseModel):
    id: str
    family_id: str | None
    name: str
    scene_prompt: str
    description: str
    tokens: dict[str, Any]
    css_vars: dict[str, str]
    is_system: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime
