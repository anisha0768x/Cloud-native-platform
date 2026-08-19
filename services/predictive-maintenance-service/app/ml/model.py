"""
MaintenanceModel: XGBoost binary classifier (failure risk within some
implicit near-term window) + root-cause extraction.

WHY root cause = feature_importance × normalized_deviation, not SHAP:
proper SHAP values would be the more rigorous per-prediction explanation,
but add a real dependency + computation cost for a demo-scale service.
This simpler approach — rank features by (how much this instance deviates
from the healthy-baseline mean, in std-units) × (how much the model
globally weights that feature) — is honest about being an approximation
(named as such in the docstring and the API response's `root_cause`
field), and is enough to answer "which reading is most responsible for
this risk score" in a way a human can sanity-check.
"""

from dataclasses import dataclass

import numpy as np
import xgboost as xgb

from app.ml.features import FEATURE_ORDER, FeatureVector

_HUMAN_LABELS = {
    "cpu_mean": "sustained high CPU usage",
    "cpu_std": "unstable/volatile CPU usage",
    "cpu_slope": "CPU usage trending upward",
    "memory_mean": "high memory usage",
    "memory_std": "unstable/volatile memory usage",
    "memory_slope": "memory usage trending upward",
    "restart_count": "elevated pod restart count",
}


@dataclass
class MaintenancePrediction:
    failure_probability: float
    root_cause: str
    recommendation: str


class MaintenanceModel:
    def __init__(self):
        self._model: xgb.XGBClassifier | None = None
        self._healthy_mean: np.ndarray | None = None
        self._healthy_std: np.ndarray | None = None

    def train(self, features: list[FeatureVector], labels: list[int]) -> None:
        X = np.array([[getattr(f, name) for name in FEATURE_ORDER] for f in features])
        y = np.array(labels)

        self._model = xgb.XGBClassifier(
            n_estimators=100,
            max_depth=4,
            learning_rate=0.1,
            eval_metric="logloss",
        )
        self._model.fit(X, y)

        # Baseline stats from HEALTHY (label==0) examples only — this is
        # what "normal" looks like, which root-cause deviation is measured
        # against.
        healthy_X = X[y == 0]
        self._healthy_mean = healthy_X.mean(axis=0)
        self._healthy_std = healthy_X.std(axis=0)
        self._healthy_std[self._healthy_std == 0] = 1.0  # avoid div-by-zero for constant features

    def predict(self, vector: FeatureVector) -> MaintenancePrediction:
        if self._model is None:
            raise RuntimeError("MaintenanceModel.train() must be called before predict()")

        x = np.array([[getattr(vector, name) for name in FEATURE_ORDER]])
        probability = float(self._model.predict_proba(x)[0][1])

        importances = self._model.feature_importances_
        deviations = np.abs((x[0] - self._healthy_mean) / self._healthy_std)
        contribution_scores = importances * deviations

        top_feature_idx = int(np.argmax(contribution_scores))
        top_feature_name = FEATURE_ORDER[top_feature_idx]
        root_cause = _HUMAN_LABELS[top_feature_name]

        recommendation = self._recommend(probability, top_feature_name, vector)

        return MaintenancePrediction(
            failure_probability=round(probability, 4),
            root_cause=root_cause,
            recommendation=recommendation,
        )

    @staticmethod
    def _recommend(probability: float, top_feature: str, vector: FeatureVector) -> str:
        if probability < 0.3:
            return "No action needed; metrics within normal range."
        if top_feature == "restart_count":
            return "Investigate recent restarts (check logs for crash loops); consider a manual restart if the root cause is transient."
        if top_feature in ("cpu_mean", "cpu_slope", "cpu_std"):
            return "Investigate CPU-bound workload; consider scaling up replicas or profiling for a runaway process."
        if top_feature in ("memory_mean", "memory_slope"):
            return "Investigate potential memory leak; consider a rolling restart and scaling up if the trend continues."
        return "Monitor closely; no single dominant factor identified."
