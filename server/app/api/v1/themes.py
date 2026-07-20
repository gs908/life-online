"""动态主题路由。"""
from __future__ import annotations

from fastapi import APIRouter

from app.deps import CurrentUser, DBSession, GuildMasterOnly
from app.schemas.common import ApiResponse, ok
from app.schemas.theme import ThemeGenerateRequest, ThemeStyleCreate, ThemeStyleRead, ThemeStyleUpdate
from app.services import theme_service

router = APIRouter(prefix="/themes", tags=["themes"])


def _to_read(theme) -> ThemeStyleRead:
    return ThemeStyleRead(
        id=theme.id,
        family_id=theme.family_id,
        name=theme.name,
        scene_prompt=theme.scene_prompt,
        description=theme.description,
        tokens=theme.tokens,
        css_vars=theme.css_vars,
        is_system=theme.is_system,
        is_active=theme.is_active,
        created_at=theme.created_at,
        updated_at=theme.updated_at,
    )


@router.get("", response_model=ApiResponse[list[ThemeStyleRead]], summary="主题列表")
async def list_themes(db: DBSession, user: CurrentUser) -> ApiResponse[list[ThemeStyleRead]]:
    rows = await theme_service.list_themes(db, family_id=user.family_id)
    return ok([_to_read(row) for row in rows])


@router.get("/{theme_id}", response_model=ApiResponse[ThemeStyleRead], summary="主题详情")
async def get_theme(theme_id: str, db: DBSession, user: CurrentUser) -> ApiResponse[ThemeStyleRead]:
    theme = await theme_service.get_theme(db, theme_id=theme_id, family_id=user.family_id)
    return ok(_to_read(theme))


@router.post("", response_model=ApiResponse[ThemeStyleRead], summary="创建家庭主题(父母)")
async def create_theme(
    body: ThemeStyleCreate, db: DBSession, user: GuildMasterOnly,
) -> ApiResponse[ThemeStyleRead]:
    theme = await theme_service.create_theme(
        db,
        family_id=user.family_id,
        name=body.name,
        scene_prompt=body.scene_prompt,
        description=body.description,
        tokens=body.tokens,
        css_vars=body.css_vars,
        is_active=body.is_active,
    )
    return ok(_to_read(theme))


@router.patch("/{theme_id}", response_model=ApiResponse[ThemeStyleRead], summary="更新家庭主题(父母)")
async def update_theme(
    theme_id: str, body: ThemeStyleUpdate, db: DBSession, user: GuildMasterOnly,
) -> ApiResponse[ThemeStyleRead]:
    theme = await theme_service.update_theme(
        db,
        theme_id=theme_id,
        family_id=user.family_id,
        name=body.name,
        scene_prompt=body.scene_prompt,
        description=body.description,
        tokens=body.tokens,
        css_vars=body.css_vars,
        is_active=body.is_active,
    )
    return ok(_to_read(theme))


@router.post("/{theme_id}/activate", response_model=ApiResponse[ThemeStyleRead], summary="激活家庭主题(父母)")
async def activate_theme(
    theme_id: str, db: DBSession, user: GuildMasterOnly,
) -> ApiResponse[ThemeStyleRead]:
    theme = await theme_service.activate_theme(db, theme_id=theme_id, family_id=user.family_id)
    return ok(_to_read(theme))


@router.delete("/{theme_id}", response_model=ApiResponse[dict], summary="删除家庭主题(父母)")
async def delete_theme(theme_id: str, db: DBSession, user: GuildMasterOnly) -> ApiResponse[dict]:
    await theme_service.delete_theme(db, theme_id=theme_id, family_id=user.family_id)
    return ok({"deleted": True})


@router.post("/generate", response_model=ApiResponse[ThemeStyleRead], summary="AI 生成家庭主题(父母)")
async def generate_theme(
    body: ThemeGenerateRequest, db: DBSession, user: GuildMasterOnly,
) -> ApiResponse[ThemeStyleRead]:
    theme = await theme_service.generate_theme(
        db,
        family_id=user.family_id,
        scene_prompt=body.scene_prompt,
        name=body.name,
        activate=body.activate,
    )
    return ok(_to_read(theme))
