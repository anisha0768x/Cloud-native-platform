"""
Synthetic LABELED training data generator.

WHY this is more fundamentally necessary here than in Traffic Prediction
Service (Module 8): that service could, in principle, train on real
historical data once enough accumulates. This service needs historical
FAILURE EXAMPLES to train a classifier — and no amount of waiting
produces those safely; you'd need real outages to have actually happened
and been recorded. Since this platform has no failure-event history table
anywhere (recording one would mean either waiting for real production
incidents, or building a whole synthetic-incident-injection system, which
is out of scope), training data here is ALWAYS synthetic, generated with
a deliberately realistic, inspectable structure: failure risk correlates
with high+rising CPU, memory near capacity, and climbing restart counts —
the same signals real SRE runbooks flag. This is documented in every API
response (there is no "historical" mode for training data in this
service, unlike Module 8) so nobody mistakes it for learned-from-real-
incidents.

What IS real: the feature vector run through this trained model at
inference time (see clients/) is live data pulled from Metrics Service
and K8s Management Service, not synthetic.
"""

import random

from app.ml.features import FeatureVector

FEATURE_NAMES = ["cpu_mean", "cpu_std", "cpu_slope", "memory_mean", "memory_std", "memory_slope", "restart_count"]


def generate_labeled_training_set(
    *, n_samples: int = 2000, seed: int = 42
) -> tuple[list[FeatureVector], list[int]]:
    rng = random.Random(seed)
    features: list[FeatureVector] = []
    labels: list[int] = []

    for _ in range(n_samples):
        # Sample a "regime" per example: healthy, degrading, or critical —
        # this is what gives the dataset real structure for the model to
        # learn, rather than pure independent random noise per feature.
        regime = rng.choices(["healthy", "degrading", "critical"], weights=[0.7, 0.2, 0.1])[0]

        if regime == "healthy":
            cpu_mean = rng.uniform(20, 55)
            cpu_slope = rng.uniform(-2, 2)
            memory_mean = rng.uniform(30, 65)
            memory_slope = rng.uniform(-1, 1)
            restart_count = rng.choices([0, 1], weights=[0.9, 0.1])[0]
            label_prob = 0.02
        elif regime == "degrading":
            cpu_mean = rng.uniform(55, 80)
            cpu_slope = rng.uniform(1, 5)
            memory_mean = rng.uniform(65, 88)
            memory_slope = rng.uniform(0.5, 3)
            restart_count = rng.choices([0, 1, 2], weights=[0.4, 0.4, 0.2])[0]
            label_prob = 0.35
        else:  # critical
            cpu_mean = rng.uniform(80, 99)
            cpu_slope = rng.uniform(2, 8)
            memory_mean = rng.uniform(88, 99)
            memory_slope = rng.uniform(1, 5)
            restart_count = rng.choices([2, 3, 4, 5], weights=[0.3, 0.3, 0.25, 0.15])[0]
            label_prob = 0.85

        cpu_std = rng.uniform(2, 15)
        memory_std = rng.uniform(2, 12)

        vector = FeatureVector(
            cpu_mean=round(cpu_mean, 2),
            cpu_std=round(cpu_std, 2),
            cpu_slope=round(cpu_slope, 2),
            memory_mean=round(memory_mean, 2),
            memory_std=round(memory_std, 2),
            memory_slope=round(memory_slope, 2),
            restart_count=restart_count,
        )
        label = 1 if rng.random() < label_prob else 0

        features.append(vector)
        labels.append(label)

    return features, labels
