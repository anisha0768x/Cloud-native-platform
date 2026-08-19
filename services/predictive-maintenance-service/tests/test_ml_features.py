from datetime import datetime, timedelta, timezone

from app.ml.features import _slope, _std, build_feature_vector
from app.ml.synthetic import generate_labeled_training_set


def test_slope_detects_upward_trend():
    assert _slope([10, 20, 30, 40, 50]) > 0


def test_slope_detects_downward_trend():
    assert _slope([50, 40, 30, 20, 10]) < 0


def test_slope_is_zero_for_flat_series():
    assert _slope([25, 25, 25, 25]) == 0


def test_std_is_zero_for_constant_series():
    assert _std([10, 10, 10]) == 0


def test_std_is_positive_for_varying_series():
    assert _std([10, 20, 30]) > 0


def test_build_feature_vector_from_series():
    now = datetime.now(timezone.utc)
    cpu_series = [(now - timedelta(hours=5 - i), v) for i, v in enumerate([50, 55, 60, 65, 70])]
    memory_series = [(now - timedelta(hours=5 - i), v) for i, v in enumerate([40, 40, 40, 40, 40])]

    vector = build_feature_vector(cpu_series=cpu_series, memory_series=memory_series, restart_count=2)

    assert vector.cpu_mean == 60.0
    assert vector.cpu_slope > 0  # rising
    assert vector.memory_std == 0  # flat series
    assert vector.restart_count == 2


def test_build_feature_vector_handles_empty_series():
    vector = build_feature_vector(cpu_series=[], memory_series=[], restart_count=0)
    assert vector.cpu_mean == 0.0
    assert vector.cpu_std == 0.0


def test_synthetic_training_set_has_requested_size():
    features, labels = generate_labeled_training_set(n_samples=500, seed=1)
    assert len(features) == 500
    assert len(labels) == 500


def test_synthetic_training_set_is_deterministic():
    a_features, a_labels = generate_labeled_training_set(n_samples=100, seed=5)
    b_features, b_labels = generate_labeled_training_set(n_samples=100, seed=5)
    assert a_labels == b_labels
    assert [f.to_dict() for f in a_features] == [f.to_dict() for f in b_features]


def test_synthetic_training_set_has_both_classes():
    _, labels = generate_labeled_training_set(n_samples=1000, seed=1)
    assert 0 in labels
    assert 1 in labels


def test_synthetic_training_set_correlates_high_cpu_with_failure_label():
    """
    Structural sanity check: examples labeled as failures should have a
    meaningfully higher average CPU than examples labeled healthy — this
    is the property the classifier is expected to learn.
    """
    features, labels = generate_labeled_training_set(n_samples=2000, seed=1)
    failure_cpu = [f.cpu_mean for f, l in zip(features, labels) if l == 1]
    healthy_cpu = [f.cpu_mean for f, l in zip(features, labels) if l == 0]
    assert sum(failure_cpu) / len(failure_cpu) > sum(healthy_cpu) / len(healthy_cpu)
