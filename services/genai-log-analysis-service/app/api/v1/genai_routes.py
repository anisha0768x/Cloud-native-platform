import uuid

from fastapi import APIRouter, Depends, Header, Query

from platform_common.security import TokenPayload, require_permission

from app.core.dependencies import get_analysis_service
from app.schemas.analysis import AnalysisHistoryEntry, AnalysisResponse
from app.services.analysis_service import GenAiAnalysisService

router = APIRouter(prefix="/api/v1/genai", tags=["genai"])


@router.get("/analyze/{service_id}", response_model=AnalysisResponse)
async def analyze(
    service_id: uuid.UUID,
    authorization: str = Header(...),
    analysis: GenAiAnalysisService = Depends(get_analysis_service),
    _: TokenPayload = Depends(require_permission("logs:read")),
):
    return await analysis.analyze(service_id=service_id, authorization=authorization)


@router.get("/history/{service_id}", response_model=list[AnalysisHistoryEntry])
async def history(
    service_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=500),
    analysis: GenAiAnalysisService = Depends(get_analysis_service),
    _: TokenPayload = Depends(require_permission("logs:read")),
):
    return await analysis.history(service_id=service_id, limit=limit)
