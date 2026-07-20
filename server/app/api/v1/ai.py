"""AI 路由:任务文案生成 / 评分。"""
from __future__ import annotations

from pydantic import BaseModel, Field

from fastapi import APIRouter

from app.deps import GuildMasterOnly
from app.schemas.common import ApiResponse, ok
from app.services import ai_service

router = APIRouter(prefix="/ai", tags=["ai"])


class GenerateQuestRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=500)
    child_level: int = Field(default=1, ge=1, le=200)
    narrative_context: str = ""


class EvaluateProofRequest(BaseModel):
    task_title: str
    image_data_url: str


@router.post("/generate-quest", response_model=ApiResponse[dict], summary="AI 生成任务文案(父母)")
async def generate_quest(body: GenerateQuestRequest, _: GuildMasterOnly) -> ApiResponse[dict]:
    data = await ai_service.generate_quest(
        topic=body.topic, child_level=body.child_level,
        narrative_context=body.narrative_context,
    )
    return ok(data)


@router.post("/evaluate-proof", response_model=ApiResponse[dict], summary="AI 评分证明(父母)")
async def evaluate_proof(body: EvaluateProofRequest, _: GuildMasterOnly) -> ApiResponse[dict]:
    data = await ai_service.evaluate_proof(
        task_title=body.task_title, image_data_url=body.image_data_url,
    )
    return ok(data)
