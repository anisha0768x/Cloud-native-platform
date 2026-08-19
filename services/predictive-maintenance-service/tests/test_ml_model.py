from app.ml.features import FeatureVector
from app.ml.model import MaintenanceModel
from app.ml.synthetic import generate_labeled_training_set


def _trained_model() -> MaintenanceModel:
    features, labels = generate_labeled_training_set(n_samples=2000, seed=42)
    model = MaintenanceModel()
    model.train(features, labels)
    return model


def test_healthy_input_predicts_low_failure_probability():
    model = _trained_model()
    healthy = FeatureVector(cpu_mean=30, cpu_std=5, cpu_slope=0.1, memory_mean=40, memory_std=5, memory_slope=0.1, restart_count=0)
    result = model.predict(healthy)
    assert result.failure_probability < 0.3
    assert "no action needed" in result.recommendation.lower()


def test_critical_input_predicts_high_failure_probability():
    model = _trained_model()
    critical = FeatureVector(cpu_mean=95, cpu_std=10, cpu_slope=6, memory_mean=95, memory_std=8, memory_slope=4, restart_count=5)
    result = model.predict(critical)
    assert result.failure_probability > 0.5


def test_probability_increases_monotonically_with_cpu():
    """Core sanity check: the model should agree that MORE stress = MORE risk."""
    model = _trained_model()
    base = dict(cpu_std=5, cpu_slope=0.5, memory_mean=40, memory_std=5, memory_slope=0.2, restart_count=0)
    low = model.predict(FeatureVector(cpu_mean=30, **base))
    high = model.predict(FeatureVector(cpu_mean=90, **base))
    assert high.failure_probability > low.failure_probability


def test_root_cause_identifies_memory_when_memory_dominant():
    model = _trained_model()
    vector = FeatureVector(cpu_mean=35, cpu_std=5, cpu_slope=0.2, memory_mean=97, memory_std=10, memory_slope=4.5, restart_count=0)
    result = model.predict(vector)
    assert "memory" in result.root_cause.lower()


def test_root_cause_identifies_restarts_when_restart_dominant():
    model = _trained_model()
    vector = FeatureVector(cpu_mean=35, cpu_std=5, cpu_slope=0.2, memory_mean=40, memory_std=5, memory_slope=0.2, restart_count=8)
    result = model.predict(vector)
    assert "restart" in result.root_cause.lower()


def test_recommendation_varies_by_root_cause():
    """
    Tests the recommendation-selection logic directly (via the model's
    static _recommend helper) rather than through a full prediction —
    that avoids depending on a specific trained model's decision boundary
    happening to cross the 0.3 action threshold for hand-picked inputs.
    """
    from app.ml.model import MaintenanceModel

    cpu_vector = FeatureVector(cpu_mean=95, cpu_std=10, cpu_slope=5, memory_mean=40, memory_std=5, memory_slope=0.2, restart_count=0)
    restart_vector = FeatureVector(cpu_mean=35, cpu_std=5, cpu_slope=0.2, memory_mean=40, memory_std=5, memory_slope=0.2, restart_count=8)
    memory_vector = FeatureVector(cpu_mean=35, cpu_std=5, cpu_slope=0.2, memory_mean=95, memory_std=8, memory_slope=4, restart_count=0)

    cpu_rec = MaintenanceModel._recommend(0.8, "cpu_mean", cpu_vector)
    restart_rec = MaintenanceModel._recommend(0.8, "restart_count", restart_vector)
    memory_rec = MaintenanceModel._recommend(0.8, "memory_mean", memory_vector)

    assert cpu_rec != restart_rec != memory_rec
    assert "cpu" in cpu_rec.lower() or "workload" in cpu_rec.lower()
    assert "restart" in restart_rec.lower()
    assert "memory" in memory_rec.lower()


def test_predict_before_train_raises():
    import pytest

    model = MaintenanceModel()
    with pytest.raises(RuntimeError):
        model.predict(FeatureVector(cpu_mean=1, cpu_std=1, cpu_slope=1, memory_mean=1, memory_std=1, memory_slope=1, restart_count=0))


def test_failure_probability_is_valid_probability():
    model = _trained_model()
    vector = FeatureVector(cpu_mean=60, cpu_std=8, cpu_slope=2, memory_mean=70, memory_std=6, memory_slope=1, restart_count=1)
    result = model.predict(vector)
    assert 0.0 <= result.failure_probability <= 1.0
