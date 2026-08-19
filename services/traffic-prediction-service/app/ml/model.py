"""
TrafficModel: trains 3 LightGBM regressors (not 1) — this is the
mechanism for the confidence interval the architecture doc's §7.1 spec
requires. A single point-forecast model has no notion of uncertainty;
quantile regression (objective="quantile", alpha=0.1/0.5/0.9) trains
three separate models predicting the 10th/50th/90th percentile of the
target directly, giving a genuine [lower, upper] interval derived from
the model's own learned uncertainty rather than a heuristic fixed
percentage band.
"""

from dataclasses import dataclass

import lightgbm as lgb
import pandas as pd

from app.ml.features import FEATURE_COLUMNS, build_feature_frame


@dataclass
class PredictionResult:
    expected: float
    lower: float
    upper: float


class TrafficModel:
    def __init__(self):
        self._models: dict[str, lgb.LGBMRegressor] = {}
        self._trained = False

    def train(self, series: list[tuple]) -> None:
        df = build_feature_frame(series)
        # Drop rows where lag features are NaN (the first `168` rows won't
        # have a full week of lag history) — training on incomplete
        # feature rows would teach the model that "unknown lag" means
        # something, which it doesn't.
        df = df.dropna(subset=FEATURE_COLUMNS)
        if len(df) < 10:
            raise ValueError("Not enough complete feature rows to train (need >= 10 after dropping NaN lags)")

        X = df[FEATURE_COLUMNS]
        y = df["value"]

        for quantile, key in [(0.1, "lower"), (0.5, "expected"), (0.9, "upper")]:
            model = lgb.LGBMRegressor(
                objective="quantile",
                alpha=quantile,
                n_estimators=100,
                max_depth=5,
                learning_rate=0.1,
                min_child_samples=5,
                verbose=-1,
            )
            model.fit(X, y)
            self._models[key] = model

        self._trained = True

    def predict(self, feature_row: pd.DataFrame) -> PredictionResult:
        if not self._trained:
            raise RuntimeError("TrafficModel.train() must be called before predict()")

        lower = max(0.0, float(self._models["lower"].predict(feature_row)[0]))
        expected = max(0.0, float(self._models["expected"].predict(feature_row)[0]))
        upper = max(0.0, float(self._models["upper"].predict(feature_row)[0]))

        # Quantile models are trained independently, so they can (rarely)
        # cross out of order on a given input — clip rather than let the
        # API return a nonsensical lower > expected.
        lower = min(lower, expected)
        upper = max(upper, expected)

        return PredictionResult(expected=round(expected, 2), lower=round(lower, 2), upper=round(upper, 2))
