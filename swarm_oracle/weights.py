"""Calibration weight derivation for the Swarm Oracle.

Given an agent's historical Brier score and number of predictions, compute a
scalar weight that the consensus engine uses to aggregate votes. Lower Brier
(better calibration) → higher weight. Few predictions → scaled down (resist
gaming via lucky guesses).

This is the off-chain reference implementation. The on-chain CalibrationRegistry
will mirror the same formula in fixed-point Solidity.

Adapter on top of `scripts/forecast_lab/scorer.py:brier_score` and
`scripts/lib/calibration.py:brier` — those produce the per-prediction Brier;
this module aggregates a history into a single per-agent weight.
"""
from __future__ import annotations

# Design-doc constants.
BASE_WEIGHT = 1.0
MIN_PREDICTIONS = 20
CONFIDENCE_THRESHOLD = 100  # predictions beyond which weight is fully credited
EPSILON = 1e-3  # smoothing so a perfect Brier (0.0) doesn't blow up
MAX_BRIER = 1.0  # Brier score is bounded in [0, 1]


def compute_weight(brier_score: float, num_predictions: int) -> float:
    """Calibration weight for an agent.

    Formula (matches design doc):

        if num_predictions < MIN_PREDICTIONS:
            weight = BASE_WEIGHT      # equal voice for new agents

        else:
            raw     = 1 / (brier + EPSILON)
            confidence = min(1, num_predictions / CONFIDENCE_THRESHOLD)
            weight  = raw * confidence

    Lower Brier → higher raw weight. More history → stronger confidence
    scaling. Combined, this rewards agents with both accuracy and a track
    record.
    """
    if not (0.0 <= brier_score <= MAX_BRIER):
        raise ValueError(
            f"brier_score {brier_score!r} must be in [0, {MAX_BRIER}]"
        )
    if num_predictions < 0:
        raise ValueError(f"num_predictions {num_predictions!r} must be >= 0")

    if num_predictions < MIN_PREDICTIONS:
        return BASE_WEIGHT

    raw = 1.0 / (brier_score + EPSILON)
    confidence = min(1.0, num_predictions / CONFIDENCE_THRESHOLD)
    return raw * confidence


def weights_from_history(history: dict[str, dict]) -> dict[str, float]:
    """Convert a registry-shaped history map to a {agent_id: weight} map.

    Input shape:
        {
            "agent_id": {"brier_score": 0.12, "num_predictions": 150},
            ...
        }

    Missing num_predictions defaults to 0 (treated as new agent → BASE_WEIGHT).
    """
    out: dict[str, float] = {}
    for agent_id, entry in history.items():
        brier = float(entry.get("brier_score", 0.25))
        n = int(entry.get("num_predictions", 0))
        out[agent_id] = compute_weight(brier, n)
    return out


def mock_brier_history() -> dict[str, dict]:
    """Return a hand-tuned mock calibration history for the Week 1 demo.

    Three agents at distinct calibration tiers, plus history depths that
    exercise the confidence-scaling branch. Replace with real Brier scores
    from the forecast pipeline post-hackathon.
    """
    return {
        "agent-oracle": {
            # Best-calibrated specialist — finance/crypto agent that has
            # been consistently right.
            "brier_score": 0.10,
            "num_predictions": 220,
        },
        "agent-reliable": {
            # Mid-tier — solid generalist, more predictions but slightly
            # less calibrated.
            "brier_score": 0.18,
            "num_predictions": 140,
        },
        "agent-novice": {
            # Lower tier — at MIN_PREDICTIONS, so confidence scaling
            # damps it down further.
            "brier_score": 0.25,
            "num_predictions": 25,
        },
    }


def update_brier_running_average(
    prior_brier: float | None,
    prior_n: int,
    prediction: float,
    outcome: float,
) -> tuple[float, int]:
    """Incrementally update an agent's running-average Brier as outcomes arrive.

    Pure function — no I/O. Caller is responsible for persisting the result.

    Returns (new_brier, new_n).
    """
    new_brier_term = (prediction - outcome) ** 2
    if prior_brier is None or prior_n == 0:
        return (new_brier_term, 1)
    new_n = prior_n + 1
    new_brier = (prior_brier * prior_n + new_brier_term) / new_n
    return (new_brier, new_n)
