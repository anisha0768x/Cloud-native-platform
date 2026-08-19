"""
FeatureVector: the tabular representation both training (synthetic) and
inference (live) data must produce, so the model never needs to know
which source a vector came from.

Slope is computed via simple linear regression (least squares) over the
series — a cheap, standard way to quantify "is this trending up" without
needing a full time-series library for what's fundamentally a straight-
line fit over a short window.
"""

from dataclasses import asdict, dataclass
from datetime import datetime


@dataclass
class FeatureVector:
    cpu_mean: float
    cpu_std: float
    cpu_slope: float
    memory_mean: float
    memory_std: float
    memory_slope: float
    restart_count: int

    def to_dict(self) -> dict:
        return asdict(self)


FEATURE_ORDER = ["cpu_mean", "cpu_std", "cpu_slope", "memory_mean", "memory_std", "memory_slope", "restart_count"]


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = _mean(values)
    variance = sum((v - m) ** 2 for v in values) / len(values)
    return variance**0.5


def _slope(values: list[float]) -> float:
    """Least-squares linear regression slope over evenly-spaced points."""
    n = len(values)
    if n < 2:
        return 0.0
    x_mean = (n - 1) / 2
    y_mean = _mean(values)
    numerator = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    denominator = sum((i - x_mean) ** 2 for i in range(n))
    return numerator / denominator if denominator else 0.0


def build_feature_vector(
    *,
    cpu_series: list[tuple[datetime, float]],
    memory_series: list[tuple[datetime, float]],
    restart_count: int,
) -> FeatureVector:
    cpu_values = [v for _, v in cpu_series]
    memory_values = [v for _, v in memory_series]

    return FeatureVector(
        cpu_mean=round(_mean(cpu_values), 2),
        cpu_std=round(_std(cpu_values), 2),
        cpu_slope=round(_slope(cpu_values), 2),
        memory_mean=round(_mean(memory_values), 2),
        memory_std=round(_std(memory_values), 2),
        memory_slope=round(_slope(memory_values), 2),
        restart_count=restart_count,
    )
