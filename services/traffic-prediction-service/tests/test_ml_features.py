from datetime import datetime, timedelta, timezone

from app.ml.features import build_feature_frame, build_prediction_features
from app.ml.synthetic import generate_synthetic_series


def test_synthetic_series_has_expected_length():
    series = generate_synthetic_series(hours=100)
    assert len(series) == 100


def test_synthetic_series_is_deterministic_given_same_seed():
    a = generate_synthetic_series(hours=48, seed=123)
    b = generate_synthetic_series(hours=48, seed=123)
    assert a == b


def test_synthetic_series_captures_daily_seasonality():
    """Mid-day traffic should be meaningfully higher than overnight traffic."""
    series = generate_synthetic_series(hours=24 * 14, seed=7)
    midday_values = [v for ts, v in series if ts.hour in (12, 13, 14)]
    overnight_values = [v for ts, v in series if ts.hour in (2, 3, 4)]
    assert sum(midday_values) / len(midday_values) > sum(overnight_values) / len(overnight_values) * 2


def test_synthetic_series_captures_weekly_seasonality():
    """Weekday traffic should be higher than weekend traffic."""
    series = generate_synthetic_series(hours=24 * 21, seed=7)
    weekday_values = [v for ts, v in series if ts.weekday() < 5]
    weekend_values = [v for ts, v in series if ts.weekday() >= 5]
    assert sum(weekday_values) / len(weekday_values) > sum(weekend_values) / len(weekend_values)


def test_build_feature_frame_has_expected_columns():
    series = generate_synthetic_series(hours=200)
    df = build_feature_frame(series)
    for col in ["hour_of_day", "day_of_week", "is_weekend", "is_holiday", "lag_1h", "lag_24h", "rolling_mean_24h"]:
        assert col in df.columns


def test_build_feature_frame_lag_1h_is_correct():
    series = generate_synthetic_series(hours=50)
    df = build_feature_frame(series)
    # lag_1h at row i should equal the raw value at row i-1
    for i in range(1, len(df)):
        assert df.loc[i, "lag_1h"] == df.loc[i - 1, "value"]


def test_build_prediction_features_returns_single_row():
    series = generate_synthetic_series(hours=200)
    target = datetime.now(timezone.utc) + timedelta(hours=1)
    features = build_prediction_features(series, target)
    assert len(features) == 1
    assert features.iloc[0]["hour_of_day"] == target.hour
