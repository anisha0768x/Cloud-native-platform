import uuid

from fastapi import APIRouter, Depends, Header, Query

from platform_common.security import TokenPayload, require_permission

from app.core.dependencies import get_prediction_service
from app.schemas.prediction import PredictionHistoryEntry, TrafficPredictionResponse
from app.services.prediction_service import PredictionService

router = APIRouter(prefix="/api/v1/predictions/traffic", tags=["traffic-prediction"])


@router.get("/{service_id}", response_model=TrafficPredictionResponse)
async def predict_traffic(
    service_id: uuid.UUID,
    horizon_hours: int = Query(default=1, ge=1, le=168),
    authorization: str = Header(...),
    predictions: PredictionService = Depends(get_prediction_service),
    _: TokenPayload = Depends(require_permission("metrics:read")),
):
    return await predictions.predict(service_id=service_id, authorization=authorization, horizon_hours=horizon_hours)


@router.get("/{service_id}/history", response_model=list[PredictionHistoryEntry])
async def prediction_history(
    service_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=500),
    predictions: PredictionService = Depends(get_prediction_service),
    _: TokenPayload = Depends(require_permission("metrics:read")),
):
    return await predictions.history(service_id=service_id, limit=limit)
