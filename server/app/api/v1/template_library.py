"""任务模板库路由:列表 / 收藏 / 套用(docs/06 §2,docs/12 块 A)。"""
from __future__ import annotations

from fastapi import APIRouter, Query

from app.deps import CurrentUser, DBSession, GuildMasterOnly
from app.schemas.common import ApiResponse, ok
from app.schemas.task import TemplateLibraryApplyRequest, TemplateLibraryRead
from app.services import task_template_service

router = APIRouter(prefix="/scn/template-library", tags=["scn-template-library"])


def _to_read(entry, favorite_of_ids: set[str] | None = None) -> TemplateLibraryRead:
    favorite_of = entry.meta.get("favorite_of") if entry.meta else None
    return TemplateLibraryRead(
        id=entry.id,
        family_id=entry.family_id,
        category=entry.category,
        tags=entry.tags or [],
        title=entry.title,
        description=entry.description,
        suggested_xp=entry.suggested_xp,
        suggested_time_deposit=entry.suggested_time_deposit,
        suggested_type=entry.suggested_type,
        is_active=entry.is_active,
        is_favorite=(
            favorite_of is not None
            or (favorite_of_ids is not None and entry.id in favorite_of_ids)
        ),
        favorite_of=favorite_of,
    )


@router.get("", response_model=ApiResponse[list[TemplateLibraryRead]], summary="模板库列表(系统预置+家庭自建)")
async def list_template_library(
    db: DBSession, user: CurrentUser,
    category: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
    favorites_only: bool = Query(default=False),
) -> ApiResponse[list[TemplateLibraryRead]]:
    entries, favorite_of_ids = await task_template_service.list_library(
        db,
        family_id=user.family_id,
        category=category,
        keyword=keyword,
        favorites_only=favorites_only,
    )
    return ok([_to_read(e, favorite_of_ids) for e in entries])


@router.get("/{entry_id}", response_model=ApiResponse[TemplateLibraryRead], summary="模板库条目详情")
async def get_template_library_entry(
    entry_id: str, db: DBSession, user: CurrentUser,
) -> ApiResponse[TemplateLibraryRead]:
    entry = await task_template_service.get_library_entry(db, entry_id)
    return ok(_to_read(entry))


@router.post(
    "/{entry_id}/favorite",
    response_model=ApiResponse[dict],
    summary="收藏/取消收藏(父母),返回切换后的收藏状态",
)
async def favorite_template_library_entry(
    entry_id: str, db: DBSession, user: GuildMasterOnly,
) -> ApiResponse[dict]:
    favorited = await task_template_service.toggle_favorite(
        db, family_id=user.family_id, entry_id=entry_id,
    )
    return ok({"entry_id": entry_id, "is_favorite": favorited})


@router.post(
    "/{entry_id}/apply",
    response_model=ApiResponse[dict],
    summary="套用模板(父母):用 suggested_* 播种新模板并立即生成",
)
async def apply_template_library_entry(
    entry_id: str, body: TemplateLibraryApplyRequest, db: DBSession, user: GuildMasterOnly,
) -> ApiResponse[dict]:
    template = await task_template_service.apply_library_entry(
        db,
        family_id=user.family_id,
        creator_id=user.id,
        entry_id=entry_id,
        season_id=body.season_id,
        target_child_id=body.target_child_id,
    )
    from app.api.v1.task_templates import _to_read

    return ok({"template": _to_read(template).model_dump(mode="json")})
