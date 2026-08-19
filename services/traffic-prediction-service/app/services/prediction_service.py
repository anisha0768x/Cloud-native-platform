"""
PredictionService: the orchestration layer tying together data source
selection, model lifecycle (train/cache/retrain), and audit persistence.

WHY an in-memory, per-process model cache rather than a proper model
registry (MLflow, S3-backed artifacts — as the master architecture doc's
§7.1 describes for a full production deployment): this service has a
single replica in local/demo deployment, and training takes well under a
second on this data volume — the complexity of a model registry buys
nothing at this scale. The moment this service needs >1 replica in
production (so every replica shares the same trained model instead of
each training its own independently), swapping this cache for a real
registry is the concrete next step, not a redesign — model training/
inference code doesn't change, only where the trained artifact lives.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.clients.metrics_client import MetricsClient
from app.ml.features import build_prediction_features
from app.ml.model import TrafficModel
from app.ml.synthetic import generate_synthetic_series
from app.repositories.prediction_repository import PredictionRepository


@dataclass
class _CachedModel:
    model: TrafficModel
    series: list[tuple[datetime, float]]
    data_source: str
    trained_at: datetime


class PredictionService:
    # Class-level cache: shared across requests within this process (see
    # module docstring for why this is an intentional simplification, not
    # an oversight).
    _model_cache: dict[str, _CachedModel] = {}

    def __init__(
        self,
        metrics_client: MetricsClient,
        repo: PredictionRepository,
        *,
        lookback_hours: int,
        min_training_points: int,
        requests_per_pod_capacity: int,
        model_cache_ttl_seconds: int,
    ):
        self._metrics = metrics_client
        self._repo = repo
        self._lookback_hours = lookback_hours
        self._min_points = min_training_points
        self._capacity = requests_per_pod_capacity
        self._cache_ttl = timedelta(seconds=model_cache_ttl_seconds)

    async def _get_or_train_model(self, service_id: str, authorization: str) -> _CachedModel:
        cached = self._model_cache.get(service_id)
        if cached and datetime.now(timezone.utc) - cached.trained_at < self._cache_ttl:
            return cached

        historical = await self._metrics.get_historical_series(
            service_id=service_id, authorization=authorization, lookback_hours=self._lookback_hours
        )

        if historical and len(historical) >= self._min_points:
            series, data_source = historical, "historical"
        else:
            series, data_source = generate_synthetic_series(hours=self._lookback_hours), "synthetic"

        model = TrafficModel()
        model.train(series)

        entry = _CachedModel(
            model=model, series=series, data_source=data_source, trained_at=datetime.now(timezone.utc)
        )
        self._model_cache[service_id] = entry
        return entry

    async def predict(
        self, *, service_id: uuid.UUID, authorization: str, horizon_hours: int = 1
    ) -> dict:
        cached = await self._get_or_train_model(str(service_id), authorization)

        target_time = datetime.now(timezone.utc) + timedelta(hours=horizon_hours)
        features = build_prediction_features(cached.series, target_time)
        result = cached.model.predict(features)

        recommended_replicas = max(1, -(-int(result.expected) // self._capacity))  # ceil division

        input_snapshot = {
            "hour_of_day": target_time.hour,
            "day_of_week": target_time.weekday(),
            "data_points_used": len(cached.series),
            "model_trained_at": cached.trained_at.isoformat(),
        }

        await self._repo.record(
            service_id=service_id,
            horizon_hours=horizon_hours,
            expected_requests=result.expected,
            confidence_lower=result.lower,
            confidence_upper=result.upper,
            recommended_replicas=recommended_replicas,
            data_source=cached.data_source,
            input_snapshot=input_snapshot,
        )

        response = {
            "service_id": service_id,
            "horizon_hours": horizon_hours,
            "expected_requests": result.expected,
            "confidence_lower": result.lower,
            "confidence_upper": result.upper,
            "recommended_replicas": recommended_replicas,
            "data_source": cached.data_source,
            "predicted_for": target_time,
        }
        return response

    async def history(self, *, service_id: uuid.UUID, limit: int = 50):
        return await self._repo.history(service_id=service_id, limit=limit)

    @classmethod
    def clear_model_cache(cls) -> None:
        """Test-only hook — production code never needs to force a retrain mid-process."""
        cls._model_cache.clear()
