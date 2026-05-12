"""Tests for swarm_oracle.weights — Brier-score-based weight computation."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from swarm_oracle import weights as W  # noqa: E402


# ---------------------------------------------------------------------------
# compute_weight — design doc formula
# ---------------------------------------------------------------------------


def test_new_agent_below_min_predictions_gets_base_weight():
    """Agents with <MIN_PREDICTIONS history use the base weight (no advantage from few lucky guesses)."""
    w = W.compute_weight(brier_score=0.05, num_predictions=5)
    assert w == pytest.approx(W.BASE_WEIGHT)


def test_lower_brier_means_higher_weight():
    """Brier 0.10 (oracle-tier) should outweigh Brier 0.25 (random-baseline)."""
    w_good = W.compute_weight(brier_score=0.10, num_predictions=200)
    w_bad = W.compute_weight(brier_score=0.25, num_predictions=200)
    assert w_good > w_bad


def test_more_history_means_more_confidence_scaling():
    """An agent with more predictions should get its full weight; few predictions get scaled down."""
    same_brier = 0.10
    w_few = W.compute_weight(brier_score=same_brier, num_predictions=20)  # at MIN
    w_many = W.compute_weight(brier_score=same_brier, num_predictions=200)
    assert w_many > w_few


def test_confidence_scaling_caps_at_threshold():
    """Beyond CONFIDENCE_THRESHOLD predictions, weight stops growing for the same Brier."""
    same_brier = 0.12
    w_at = W.compute_weight(brier_score=same_brier, num_predictions=W.CONFIDENCE_THRESHOLD)
    w_beyond = W.compute_weight(brier_score=same_brier, num_predictions=W.CONFIDENCE_THRESHOLD * 5)
    assert w_at == pytest.approx(w_beyond)


def test_zero_brier_does_not_explode():
    """Perfect Brier should not divide by zero — epsilon smoothing must apply."""
    w = W.compute_weight(brier_score=0.0, num_predictions=200)
    assert math_is_finite(w)
    assert w > 0


def test_random_baseline_brier_25():
    """Brier 0.25 is the dart-throwing baseline; weight there is meaningful but not dominant."""
    w_baseline = W.compute_weight(brier_score=0.25, num_predictions=200)
    w_oracle = W.compute_weight(brier_score=0.10, num_predictions=200)
    # Oracle should have a meaningfully higher weight than random
    assert w_oracle / w_baseline >= 2.0


def test_negative_or_invalid_brier_raises():
    with pytest.raises(ValueError):
        W.compute_weight(brier_score=-0.1, num_predictions=100)
    with pytest.raises(ValueError):
        W.compute_weight(brier_score=1.5, num_predictions=100)


def test_negative_predictions_raises():
    with pytest.raises(ValueError):
        W.compute_weight(brier_score=0.1, num_predictions=-5)


# ---------------------------------------------------------------------------
# weights_from_history — registry-shaped input
# ---------------------------------------------------------------------------


def test_weights_from_history_returns_dict_keyed_by_agent():
    history = {
        "alpha": {"brier_score": 0.10, "num_predictions": 200},
        "beta": {"brier_score": 0.20, "num_predictions": 100},
        "gamma": {"brier_score": 0.30, "num_predictions": 50},
    }
    weights = W.weights_from_history(history)
    assert set(weights.keys()) == {"alpha", "beta", "gamma"}
    assert weights["alpha"] > weights["beta"] > weights["gamma"]


def test_weights_from_history_handles_missing_predictions():
    """Missing num_predictions field defaults to 0 (new agent)."""
    history = {
        "newbie": {"brier_score": 0.10},
    }
    weights = W.weights_from_history(history)
    assert weights["newbie"] == pytest.approx(W.BASE_WEIGHT)


# ---------------------------------------------------------------------------
# mock_brier_history — seed for the demo
# ---------------------------------------------------------------------------


def test_mock_brier_history_has_diverse_agents():
    """Demo seeds should produce 3+ agents with distinct calibration tiers."""
    history = W.mock_brier_history()
    assert len(history) >= 3
    briers = [v["brier_score"] for v in history.values()]
    # Tiers should differ — not all equal
    assert max(briers) - min(briers) >= 0.05


def test_mock_brier_history_passes_min_predictions():
    """Mock agents should already have enough history to count."""
    history = W.mock_brier_history()
    for entry in history.values():
        assert entry["num_predictions"] >= W.MIN_PREDICTIONS


# ---------------------------------------------------------------------------
# update_brier_running_average — incremental Brier updates as outcomes arrive
# ---------------------------------------------------------------------------


def test_update_brier_running_average_first_prediction():
    new_brier, new_n = W.update_brier_running_average(
        prior_brier=None, prior_n=0, prediction=0.8, outcome=1.0
    )
    assert new_n == 1
    assert new_brier == pytest.approx((0.8 - 1.0) ** 2)


def test_update_brier_running_average_subsequent_predictions():
    # Start with prior brier of 0.04 over 1 prediction (the (0.8-1.0)^2 case)
    prior_brier = 0.04
    prior_n = 1
    # New prediction: predicted 0.3, outcome 0 — Brier on this = 0.09
    new_brier, new_n = W.update_brier_running_average(
        prior_brier=prior_brier, prior_n=prior_n, prediction=0.3, outcome=0.0
    )
    assert new_n == 2
    # Average of 0.04 and 0.09 → 0.065
    assert new_brier == pytest.approx((0.04 + 0.09) / 2)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def math_is_finite(x: float) -> bool:
    import math
    return math.isfinite(x)
