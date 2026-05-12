"""Calibration-weighted consensus aggregation for the Swarm Oracle protocol.

Given a set of probability votes from multiple agents and per-agent calibration
weights (derived from Brier scores), produce a single weighted-consensus
probability and a resolution decision (YES / NO / DISPUTE).

Pure functions — no I/O, no LLM calls, no DB. Designed to be trivially testable
and reproducible. Off-chain aggregation; on-chain verification consumes the
output.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable

# Default thresholds (overridable per-call)
DEFAULT_YES_THRESHOLD = 0.85
DEFAULT_NO_THRESHOLD = 0.15
# Standard deviation across vote probabilities above which we flag DISPUTE
# even if the weighted mean is itself extreme. ~0.20 means agents disagreeing
# by ±0.20 around the mean — a real divergence, not noise.
DEFAULT_VARIANCE_THRESHOLD = 0.20
# Default weight for agents we have no calibration history on (BASE_WEIGHT
# from design doc — equal voice for new agents).
NEW_AGENT_WEIGHT = 1.0


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Evidence:
    """A single piece of evidence cited by an agent."""

    source: str
    snippet: str
    timestamp: str | None = None
    source_type: str = "web"
    confidence: float = 0.5


@dataclass(frozen=True)
class AgentVote:
    """One agent's verification result for a question."""

    agent_id: str
    probability: float  # P(YES), in [0, 1]
    confidence: float  # Meta-confidence in own estimate, in [0, 1]
    evidence: list[Evidence] = field(default_factory=list)
    reasoning: str = ""
    research_strategy: str = "unknown"


@dataclass(frozen=True)
class Contribution:
    """Per-agent contribution to the consensus, for transparency."""

    agent_id: str
    probability: float
    weight: float
    normalized_weight: float


@dataclass(frozen=True)
class ConsensusResult:
    """Output of consensus aggregation."""

    probability: float  # Weighted consensus probability of YES
    decision: str  # "YES" | "NO" | "DISPUTE"
    num_votes: int
    contributions: list[Contribution]
    variance: float  # Sample variance across vote probabilities
    dispute_reason: str | None = None


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def aggregate_consensus(
    votes: list[AgentVote],
    weights: dict[str, float],
    *,
    yes_threshold: float = DEFAULT_YES_THRESHOLD,
    no_threshold: float = DEFAULT_NO_THRESHOLD,
    variance_threshold: float = DEFAULT_VARIANCE_THRESHOLD,
    default_weight: float = NEW_AGENT_WEIGHT,
) -> ConsensusResult:
    """Calibration-weighted linear opinion pool.

    consensus_p = Σ (w_i / Σw) * p_i

    Returns a ConsensusResult with the probability, threshold-based decision,
    per-agent contributions, and dispute metadata.

    If all weights are zero, falls back to an unweighted mean rather than
    dividing by zero — the caller still gets a useful answer.
    """
    if not votes:
        raise ValueError("aggregate_consensus needs at least one vote")

    raw_weights = [
        max(0.0, float(weights.get(v.agent_id, default_weight))) for v in votes
    ]
    total_weight = sum(raw_weights)

    if total_weight <= 0.0:
        # Degenerate case: no calibration → equal vote for everyone.
        n = len(votes)
        normalized = [1.0 / n] * n
        contributions = [
            Contribution(
                agent_id=v.agent_id,
                probability=v.probability,
                weight=0.0,
                normalized_weight=norm,
            )
            for v, norm in zip(votes, normalized)
        ]
        prob = sum(v.probability for v in votes) / n
    else:
        normalized = [w / total_weight for w in raw_weights]
        contributions = [
            Contribution(
                agent_id=v.agent_id,
                probability=v.probability,
                weight=rw,
                normalized_weight=nw,
            )
            for v, rw, nw in zip(votes, raw_weights, normalized)
        ]
        prob = sum(v.probability * nw for v, nw in zip(votes, normalized))

    # Weight-aware variance: a low-weight abstainer should not drive a dispute
    # flag. With equal weights this collapses to ordinary population variance.
    variance = _weighted_variance(
        [v.probability for v in votes], normalized, mean=prob
    )
    decision, dispute_reason = _classify(
        prob,
        variance,
        yes_threshold=yes_threshold,
        no_threshold=no_threshold,
        variance_threshold=variance_threshold,
    )

    return ConsensusResult(
        probability=prob,
        decision=decision,
        num_votes=len(votes),
        contributions=contributions,
        variance=variance,
        dispute_reason=dispute_reason,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _variance(xs: Iterable[float]) -> float:
    """Population variance (no Bessel's correction — we have all the votes)."""
    xs = list(xs)
    n = len(xs)
    if n == 0:
        return 0.0
    mean = sum(xs) / n
    return sum((x - mean) ** 2 for x in xs) / n


def _weighted_variance(
    xs: list[float], weights: list[float], mean: float
) -> float:
    """Variance weighted by per-agent normalized calibration weights.

    Equivalent to E_w[(X - mean)²] when `weights` sums to 1. Falls back to
    plain population variance when all weights are zero.
    """
    total = sum(weights)
    if total <= 0.0:
        return _variance(xs)
    return sum(w * (x - mean) ** 2 for x, w in zip(xs, weights)) / total


def _classify(
    probability: float,
    variance: float,
    *,
    yes_threshold: float,
    no_threshold: float,
    variance_threshold: float,
) -> tuple[str, str | None]:
    """Decide YES / NO / DISPUTE and optionally explain a dispute."""
    std = math.sqrt(variance)

    if std > variance_threshold:
        return (
            "DISPUTE",
            f"high variance across agents (std={std:.3f} > {variance_threshold:.2f})",
        )

    if probability >= yes_threshold:
        return ("YES", None)
    if probability <= no_threshold:
        return ("NO", None)

    return (
        "DISPUTE",
        f"weighted probability {probability:.3f} between thresholds "
        f"[{no_threshold:.2f}, {yes_threshold:.2f}]",
    )
