"""
Synthetic traffic generator — used ONLY when a service has fewer than
MIN_TRAINING_POINTS real historical data points from Metrics Service (see
PredictionService._get_training_data). This is the same "cold start"
problem every real traffic-forecasting system has on day one before
enough production data accumulates; rather than block this module on
weeks of real traffic, or fake a "trained" model, we train on realistic
synthetic data and REPORT that honestly (`data_source: "synthetic"` in
every response) until real data takes over automatically.

The pattern here: daily seasonality (business-hours peak), weekly
seasonality (weekday > weekend), plus noise — deliberately simple and
inspectable, not a black box, since the whole point is that a reviewer
can verify by eye that a model trained on this actually captures
seasonality (see tests/test_synthetic.py).
"""

import math
import random
from datetime import datetime, timedelta, timezone


def generate_synthetic_series(
    *, hours: int = 24 * 21, points_per_hour: int = 1, seed: int = 42
) -> list[tuple[datetime, float]]:
    """
    Returns [(timestamp, request_count), ...] spanning `hours` hours
    ending now, deterministic given `seed` (so tests can assert on it).
    """
    rng = random.Random(seed)
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    start = now - timedelta(hours=hours)

    series: list[tuple[datetime, float]] = []
    total_points = hours * points_per_hour
    for i in range(total_points):
        ts = start + timedelta(hours=i / points_per_hour)
        hour_of_day = ts.hour
        day_of_week = ts.weekday()  # 0=Monday .. 6=Sunday
        is_weekend = day_of_week >= 5

        # Daily curve: peaks mid-day, trough overnight (smooth sinusoid
        # centered on 14:00, floor near-zero at 02:00-04:00).
        daily_factor = max(0.15, math.sin((hour_of_day - 6) / 24 * 2 * math.pi) * 0.5 + 0.5)

        weekly_factor = 0.55 if is_weekend else 1.0

        base_load = 500.0
        value = base_load * daily_factor * weekly_factor
        # Multiplicative noise (traffic noise scales with volume, not
        # constant — realistic for request-count data).
        value *= rng.uniform(0.85, 1.15)

        series.append((ts, round(max(value, 0.0), 2)))

    return series
