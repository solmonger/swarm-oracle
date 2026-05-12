"""Tests for swarm_oracle.consensus — calibration-weighted consensus aggregation."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from swarm_oracle import consensus as C  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def vote(agent_id: str, p: float, conf: float = 0.8, evidence: list | None = None) -> C.AgentVote:
    return C.AgentVote(
        agent_id=agent_id,
        probability=p,
        confidence=conf,
        evidence=evidence or [],
        reasoning="(test)",
    )


# ---------------------------------------------------------------------------
# aggregate_consensus — weighted average
# ---------------------------------------------------------------------------


def test_aggregate_with_equal_weights_returns_simple_mean():
    votes = [vote("a", 0.6), vote("b", 0.8), vote("c", 0.7)]
    weights = {"a": 1.0, "b": 1.0, "c": 1.0}
    result = C.aggregate_consensus(votes, weights)
    assert result.probability == pytest.approx((0.6 + 0.8 + 0.7) / 3)


def test_aggregate_weights_higher_calibration_more():
    # Agent a is heavily weighted (low Brier), should dominate
    votes = [vote("a", 0.95), vote("b", 0.1), vote("c", 0.1)]
    weights = {"a": 10.0, "b": 1.0, "c": 1.0}
    result = C.aggregate_consensus(votes, weights)
    # Weighted mean: (10*0.95 + 1*0.1 + 1*0.1) / 12 = 9.7/12
    assert result.probability == pytest.approx(9.7 / 12.0)
    # And it should resolve YES (above 0.85? actually 0.808 → DISPUTE)
    # We're testing weighted math here, not threshold.


def test_aggregate_normalizes_weights_internally():
    votes = [vote("a", 0.9), vote("b", 0.5)]
    # Same ratios, different magnitudes → same result
    r1 = C.aggregate_consensus(votes, {"a": 2.0, "b": 1.0})
    r2 = C.aggregate_consensus(votes, {"a": 200.0, "b": 100.0})
    assert r1.probability == pytest.approx(r2.probability)


def test_missing_weight_uses_default_weight():
    """Agent with no weight in registry gets default (NEW_AGENT_WEIGHT)."""
    votes = [vote("a", 0.9), vote("unknown", 0.1)]
    weights = {"a": 1.0}  # "unknown" missing
    result = C.aggregate_consensus(votes, weights)
    # Both should contribute (default is BASE_WEIGHT=1.0); plain mean
    assert result.probability == pytest.approx(0.5)


def test_empty_votes_raises():
    with pytest.raises(ValueError, match="at least one vote"):
        C.aggregate_consensus([], {})


def test_zero_total_weight_falls_back_to_unweighted_mean():
    votes = [vote("a", 0.4), vote("b", 0.6)]
    # All weights zero — implementation must not divide by zero
    result = C.aggregate_consensus(votes, {"a": 0.0, "b": 0.0})
    assert result.probability == pytest.approx(0.5)


def test_single_vote_returns_that_probability():
    votes = [vote("only", 0.73)]
    result = C.aggregate_consensus(votes, {"only": 1.0})
    assert result.probability == pytest.approx(0.73)


# ---------------------------------------------------------------------------
# Resolution decision (threshold logic)
# ---------------------------------------------------------------------------


def test_high_consensus_resolves_yes():
    votes = [vote(f"a{i}", 0.9) for i in range(3)]
    weights = {f"a{i}": 1.0 for i in range(3)}
    result = C.aggregate_consensus(votes, weights)
    assert result.decision == "YES"


def test_low_consensus_resolves_no():
    votes = [vote(f"a{i}", 0.05) for i in range(3)]
    weights = {f"a{i}": 1.0 for i in range(3)}
    result = C.aggregate_consensus(votes, weights)
    assert result.decision == "NO"


def test_middle_consensus_disputes():
    votes = [vote(f"a{i}", 0.5) for i in range(3)]
    weights = {f"a{i}": 1.0 for i in range(3)}
    result = C.aggregate_consensus(votes, weights)
    assert result.decision == "DISPUTE"


def test_threshold_yes_at_default_boundary():
    # Default YES threshold is 0.85 — just above should resolve, just below should dispute
    votes_above = [vote("a", 0.86)]
    votes_below = [vote("a", 0.84)]
    weights = {"a": 1.0}
    assert C.aggregate_consensus(votes_above, weights).decision == "YES"
    assert C.aggregate_consensus(votes_below, weights).decision == "DISPUTE"


def test_custom_thresholds_override_defaults():
    votes = [vote("a", 0.7)]
    result = C.aggregate_consensus(
        votes, {"a": 1.0}, yes_threshold=0.65, no_threshold=0.35
    )
    assert result.decision == "YES"


# ---------------------------------------------------------------------------
# Dispute detection — disagreement among agents
# ---------------------------------------------------------------------------


def test_dispute_when_agents_strongly_disagree():
    """Even if weighted mean is in YES range, large disagreement triggers DISPUTE."""
    # 3 agents say strong YES (0.95), 1 high-weight agent says strong NO (0.05).
    votes = [vote("a", 0.95), vote("b", 0.95), vote("c", 0.95), vote("d", 0.05)]
    # Heavy weight on dissenter — weighted mean lands in DISPUTE zone naturally,
    # but more importantly the spread should also flag dispute.
    weights = {"a": 1.0, "b": 1.0, "c": 1.0, "d": 5.0}
    result = C.aggregate_consensus(votes, weights)
    assert result.decision == "DISPUTE"
    assert result.dispute_reason is not None


def test_high_variance_disputes_even_when_mean_extreme():
    # Mean lands at 0.86 (YES territory) but agents wildly disagree
    votes = [vote("a", 0.99), vote("b", 0.99), vote("c", 0.99), vote("d", 0.50)]
    weights = {"a": 1.0, "b": 1.0, "c": 1.0, "d": 1.0}
    result = C.aggregate_consensus(votes, weights)
    # std-dev across (0.99, 0.99, 0.99, 0.50) is ~0.21 — above default threshold
    assert result.decision == "DISPUTE"
    assert "variance" in (result.dispute_reason or "").lower() or "spread" in (
        result.dispute_reason or ""
    ).lower()


def test_no_dispute_when_agents_agree_strongly():
    votes = [vote(f"a{i}", 0.93 + i * 0.01) for i in range(4)]
    weights = {f"a{i}": 1.0 for i in range(4)}
    result = C.aggregate_consensus(votes, weights)
    assert result.decision == "YES"
    assert result.dispute_reason is None


# ---------------------------------------------------------------------------
# Result transparency — individual contributions visible
# ---------------------------------------------------------------------------


def test_result_records_individual_contributions():
    votes = [vote("a", 0.9), vote("b", 0.5)]
    weights = {"a": 3.0, "b": 1.0}
    result = C.aggregate_consensus(votes, weights)
    assert len(result.contributions) == 2
    a_contrib = next(c for c in result.contributions if c.agent_id == "a")
    assert a_contrib.probability == 0.9
    assert a_contrib.weight == 3.0
    assert a_contrib.normalized_weight == pytest.approx(0.75)


def test_result_carries_vote_count():
    votes = [vote(f"a{i}", 0.5) for i in range(5)]
    weights = {f"a{i}": 1.0 for i in range(5)}
    result = C.aggregate_consensus(votes, weights)
    assert result.num_votes == 5
