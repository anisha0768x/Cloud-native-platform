"""
MaintenanceService: orchestration layer.

WHY the model is trained ONCE per process (a single shared model, not
per-service like Traffic Prediction Service's per-service models): the
classifier learns a general "what does resource exhaustion look like"
pattern from synthetic data — it isn't specific to any one service's
traffic shape the way a traffic forecast is. One shared model applied to
each service's live feature vector is both simpler and more honest about
what's actually being modeled here.
"""

import asyncio
import uuid
from datetime import datetime, timezone

from app.clients.k8s_client import K8sClient
from app.clients.metrics_client import MetricsClient
from app.ml.features import build_feature_vector
from app.ml.model import MaintenanceModel
from app.ml.synthetic import generate_labeled_training_set
from app.repositories.maintenance_repository import MaintenancePredictionRepository


class MaintenanceService:
    _cached_model: MaintenanceModel | None = None
    _model_trained_at: datetime | None = None

    def __init__(
        self,
        metrics_client: MetricsClient,
        k8s_client: K8sClient,
        repo: MaintenancePredictionRepository,
        *,
        feature_lookback_hours: int,
        training_sample_count: int,
        model_cache_ttl_seconds: int,
    ):
        self._metrics = metrics_client
        self._k8s = k8s_client
        self._repo = repo
        self._lookback_hours = feature_lookback_hours
        self._training_samples = training_sample_count
        self._cache_ttl_seconds = model_cache_ttl_seconds

    def _get_or_train_model(self) -> MaintenanceModel:
        now = datetime.now(timezone.utc)
        cls = type(self)
        if (
            cls._cached_model is not None
            and cls._model_trained_at is not None
            and (now - cls._model_trained_at).total_seconds() < self._cache_ttl_seconds
        ):
            return cls._cached_model

        features, labels = generate_labeled_training_set(n_samples=self._training_samples)
        model = MaintenanceModel()
        model.train(features, labels)

        cls._cached_model = model
        cls._model_trained_at = now
        return model

    async def predict(self, *, service_id: uuid.UUID, service_name: str, authorization: str) -> dict:
        cpu_series, memory_series, restart_count = await self._gather_live_features(
            service_id=str(service_id), service_name=service_name, authorization=authorization
        )

        vector = build_feature_vector(
            cpu_series=cpu_series or [], memory_series=memory_series or [], restart_count=restart_count or 0
        )

        model = self._get_or_train_model()
        result = model.predict(vector)

        feature_snapshot = vector.to_dict()
        feature_snapshot["cpu_data_points"] = len(cpu_series or [])
        feature_snapshot["memory_data_points"] = len(memory_series or [])

        await self._repo.record(
            service_id=service_id,
            failure_probability=result.failure_probability,
            root_cause=result.root_cause,
            recommendation=result.recommendation,
            input_snapshot=feature_snapshot,
        )

        return {
            "service_id": service_id,
            "failure_probability": result.failure_probability,
            "root_cause": result.root_cause,
            "recommendation": result.recommendation,
            "feature_snapshot": feature_snapshot,
        }

    async def _gather_live_features(self, *, service_id: str, service_name: str, authorization: str):
        cpu_task = self._metrics.get_recent_series(
            service_id=service_id, metric_name="cpu_usage", authorization=authorization, lookback_hours=self._lookback_hours
        )
        memory_task = self._metrics.get_recent_series(
            service_id=service_id, metric_name="memory_pct", authorization=authorization, lookback_hours=self._lookback_hours
        )
        restart_task = self._k8s.get_total_restart_count(service_name=service_name, authorization=authorization)

        cpu_series, memory_series, restart_count = await asyncio.gather(cpu_task, memory_task, restart_task)
        return cpu_series, memory_series, restart_count

    async def history(self, *, service_id: uuid.UUID, limit: int = 50):
        return await self._repo.history(service_id=service_id, limit=limit)

    @classmethod
    def clear_model_cache(cls) -> None:
        """Test-only hook."""
        cls._cached_model = None
        cls._model_trained_at = None
