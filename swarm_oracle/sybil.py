"""Sybil-resistance analysis for the Swarm Oracle protocol.

This module quantifies the economic security of calibration-weighted consensus
against an attacker who tries to flip a resolution by injecting Sybil agents.

The headline result is that the protocol forces a would-be Sybil into a
dilemma:

1. *Use many low-calibration (base-weight) agents.* Cheap to spin up in raw
   count but each contributes only `BASE_WEIGHT = 1.0`. The number of Sybils
   needed grows linearly with the honest swarm's effective weight, and every
   registered agent costs gas on Base Sepolia.

2. *Build calibration first, then attack.* A Sybil that always votes a
   constant ``p`` achieves at best ``E[Brier] = p(1-p)`` (when ``p`` matches
   the base rate), capping its weight at ``~1/(p(1-p) + EPSILON)``. Reaching
   oracle-tier weight requires a Brier < 0.10 — i.e. genuinely good
   predictions, at which point the Sybil is indistinguishable from an honest
   agent and being correctly weighted by the protocol.

Both branches of the dilemma are quantified by the functions in this module.
All functions are pure (no I/O, no LLM calls) and mirror the on-chain
``CalibrationRegistry`` math. See ``docs/security-model.md`` for the writeup.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Literal

from . import consensus as _consensus
from . import weights as _weights

DecisionLiteral = Literal["YES", "NO", "DISPUTE"]

# Sentinel large weight used when an outcome is already decided and no
# attacker stake is needed. Selected to overflow no realistic float math.
_INFINITY_PREDICTIONS = float("inf")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AttackScenario:
    """Inputs for a Sybil-flip cost calculation.

    Attributes:
        honest_votes: The votes from the honest swarm — same shape used by
            ``consensus.aggregate_consensus``.
        honest_weights: Calibration weights for each honest agent (must cover
            every ``agent_id`` in ``honest_votes``; agents missing from the
            map are scored at ``default_weight``).
        target_decision: The decision the attacker wants the protocol to
            announce.
        attacker_vote: The probability each Sybil casts. Default 1.0 for a
            YES-flip target, 0.0 for NO. Use 0.5 explicitly to model a
            dispute-injecting Sybil whose only goal is to widen variance.
        yes_threshold: Protocol parameter (defaults to ``DEFAULT_YES_THRESHOLD``).
        no_threshold: Protocol parameter.
        variance_threshold: Protocol parameter (defaults to
            ``DEFAULT_VARIANCE_THRESHOLD``).
        default_weight: Weight assigned to votes whose ``agent_id`` is missing
            from ``honest_weights``. Defaults to ``NEW_AGENT_WEIGHT``.
    """

    honest_votes: list[_consensus.AgentVote]
    honest_weights: dict[str, float]
    target_decision: DecisionLiteral
    attacker_vote: float | None = None
    yes_threshold: float = _consensus.DEFAULT_YES_THRESHOLD
    no_threshold: float = _consensus.DEFAULT_NO_THRESHOLD
    variance_threshold: float = _consensus.DEFAULT_VARIANCE_THRESHOLD
    default_weight: float = _consensus.NEW_AGENT_WEIGHT

    def __post_init__(self) -> None:
        if not self.honest_votes:
            raise ValueError("AttackScenario requires at least one honest vote")
        if self.target_decision not in ("YES", "NO", "DISPUTE"):
            raise ValueError(
                f"target_decision must be YES, NO, or DISPUTE — got "
                f"{self.target_decision!r}"
            )
        v = self.attacker_vote
        if v is not None and not (0.0 <= v <= 1.0):
            raise ValueError(f"attacker_vote {v!r} must be in [0, 1]")


@dataclass(frozen=True)
class AttackResult:
    """Outcome of a Sybil-flip calculation.

    Attributes:
        is_feasible: True if the attacker can reach the target decision by
            adding Sybils with the given per-Sybil weight; False if no finite
            number of Sybils can flip the decision under the current
            protocol parameters.
        min_total_sybil_weight: Minimum aggregate Sybil weight required to
            reach the target decision. ``0.0`` if the swarm already produces
            the target decision; ``math.inf`` if infeasible.
        min_base_weight_sybils: Minimum *count* of base-weight (``1.0``)
            Sybils required, assuming each Sybil is a fresh registry entry
            (``num_predictions < MIN_PREDICTIONS``). ``math.inf`` if
            infeasible. ``int`` if finite.
        baseline_decision: The decision the honest swarm produces before the
            attack — useful for "no-op attack" reporting.
        baseline_probability: The honest swarm's weighted consensus
            probability.
        attacker_vote_used: The vote each Sybil casts in the optimal
            attack (mirrors ``AttackScenario.attacker_vote`` when set,
            otherwise the inferred value).
        notes: Free-form human-readable notes on infeasibility, dominant
            constraints, or special cases.
    """

    is_feasible: bool
    min_total_sybil_weight: float
    min_base_weight_sybils: float | int
    baseline_decision: DecisionLiteral
    baseline_probability: float
    attacker_vote_used: float
    notes: str = ""


# ---------------------------------------------------------------------------
# Public API — attack-cost calculators
# ---------------------------------------------------------------------------


def baseline_consensus(scenario: AttackScenario) -> _consensus.ConsensusResult:
    """Run the honest-only consensus for a scenario.

    Centralized so every helper in this module agrees on what the honest
    swarm would say before any Sybil enters the picture.
    """
    return _consensus.aggregate_consensus(
        scenario.honest_votes,
        scenario.honest_weights,
        yes_threshold=scenario.yes_threshold,
        no_threshold=scenario.no_threshold,
        variance_threshold=scenario.variance_threshold,
        default_weight=scenario.default_weight,
    )


def min_weight_to_flip(scenario: AttackScenario) -> AttackResult:
    """Minimum aggregate Sybil weight needed to reach ``target_decision``.

    Mathematics: the consensus is a weighted linear opinion pool

        p(new) = (Σ_h w_h p_h  +  W_s * p_s) / (Σ_h w_h  +  W_s)

    where ``W_s`` is total Sybil weight and ``p_s`` is the Sybil vote. Given
    ``A_h = Σ_h w_h p_h`` and ``W_h = Σ_h w_h``, flipping to a YES decision
    (``p(new) ≥ yes_threshold``) requires:

        A_h + W_s p_s ≥ yes_threshold · (W_h + W_s)
        =>  W_s · (p_s − yes_threshold) ≥ yes_threshold · W_h − A_h

    With the optimal attacker vote ``p_s = 1`` (for a YES target), this gives

        W_s ≥ (yes_threshold · W_h − A_h) / (1 − yes_threshold)

    Symmetrically for NO, with ``p_s = 0``:

        W_s ≥ (A_h − no_threshold · W_h) / no_threshold

    For a DISPUTE target the attacker has two routes:
      a) Drive the consensus probability between ``no_threshold`` and
         ``yes_threshold`` (the "uncertainty band").
      b) Inflate variance above ``variance_threshold`` without crossing the
         band.
    We return the cheaper of the two.

    Edge cases:
      - If the honest swarm already produces the target decision: cost = 0.
      - If the attacker's vote is on the wrong side of the threshold
        (``p_s < yes_threshold`` for a YES attack): infeasible; returns
        ``is_feasible=False``.
    """
    baseline = baseline_consensus(scenario)
    if baseline.decision == scenario.target_decision:
        return AttackResult(
            is_feasible=True,
            min_total_sybil_weight=0.0,
            min_base_weight_sybils=0,
            baseline_decision=baseline.decision,  # type: ignore[arg-type]
            baseline_probability=baseline.probability,
            attacker_vote_used=(
                scenario.attacker_vote if scenario.attacker_vote is not None
                else _default_attacker_vote(scenario.target_decision)
            ),
            notes="Honest swarm already produces target decision; no attack needed.",
        )

    p_s = (
        scenario.attacker_vote
        if scenario.attacker_vote is not None
        else _default_attacker_vote(scenario.target_decision)
    )

    if scenario.target_decision == "YES":
        result = _solve_threshold_flip(
            scenario=scenario,
            attacker_vote=p_s,
            target_low=scenario.yes_threshold,
            target_high=1.0,
            descending=False,
        )
    elif scenario.target_decision == "NO":
        result = _solve_threshold_flip(
            scenario=scenario,
            attacker_vote=p_s,
            target_low=0.0,
            target_high=scenario.no_threshold,
            descending=True,
        )
    else:  # DISPUTE
        result = _solve_dispute(scenario=scenario, attacker_vote=p_s)

    return AttackResult(
        is_feasible=result.is_feasible,
        min_total_sybil_weight=result.min_total_sybil_weight,
        min_base_weight_sybils=(
            math.inf
            if not result.is_feasible
            else math.ceil(result.min_total_sybil_weight)
        ),
        baseline_decision=baseline.decision,  # type: ignore[arg-type]
        baseline_probability=baseline.probability,
        attacker_vote_used=p_s,
        notes=result.notes,
    )


def min_sybils_to_flip(scenario: AttackScenario) -> AttackResult:
    """Alias for ``min_weight_to_flip`` — clarifies the "count of base-weight
    agents" framing used in the writeup. The two functions return the same
    ``AttackResult``; reading ``min_base_weight_sybils`` gives the count.
    """
    return min_weight_to_flip(scenario)


# ---------------------------------------------------------------------------
# Calibration-side security: how hard is it to *earn* a high Sybil weight?
# ---------------------------------------------------------------------------


def expected_brier_constant_voter(
    sybil_vote: float, base_rate: float
) -> float:
    """Expected Brier score of a Sybil that always votes the same probability.

    A Sybil that picks one ``p`` and votes it forever sees outcomes that
    resolve YES with probability ``base_rate``. Its per-prediction Brier is
    ``(p - outcome)²`` and the expectation is:

        E[Brier] = (1 − base_rate) · p²  +  base_rate · (1 − p)²

    The minimum over ``p`` is achieved at ``p = base_rate``, where
    ``E[Brier] = base_rate · (1 − base_rate)``.
    """
    _check_unit_interval("sybil_vote", sybil_vote)
    _check_unit_interval("base_rate", base_rate)
    return (1.0 - base_rate) * sybil_vote**2 + base_rate * (1.0 - sybil_vote) ** 2


def min_expected_brier_constant_voter(base_rate: float) -> float:
    """The lowest expected Brier any constant-vote Sybil can achieve.

    Equals ``base_rate · (1 - base_rate)`` — variance of a Bernoulli, which
    is exactly the irreducible loss of guessing the mean. Caps the attainable
    Sybil weight from above.
    """
    _check_unit_interval("base_rate", base_rate)
    return base_rate * (1.0 - base_rate)


def max_calibration_weight_constant_voter(base_rate: float) -> float:
    """Largest calibration weight a constant-vote Sybil can ever achieve.

    Combines ``min_expected_brier_constant_voter`` with the protocol's
    ``compute_weight`` formula at full ``CONFIDENCE_THRESHOLD`` predictions.
    """
    brier = min_expected_brier_constant_voter(base_rate)
    return _weights.compute_weight(brier, _weights.CONFIDENCE_THRESHOLD)


def sybil_break_even_predictions(
    target_weight: float, sybil_brier: float
) -> float:
    """Predictions needed for a Sybil with ``sybil_brier`` to reach ``target_weight``.

    From ``compute_weight``:

        weight = (1 / (brier + EPSILON)) · min(1, n / CONFIDENCE_THRESHOLD)

    Solving for ``n`` given a target weight:

        n = target_weight · (brier + EPSILON) · CONFIDENCE_THRESHOLD

    Returns ``math.inf`` if the Sybil cannot reach the target with any
    history depth (i.e. ``target_weight > 1/(brier + EPSILON)``). Returns
    ``MIN_PREDICTIONS`` minimum if the math would suggest fewer — under
    ``MIN_PREDICTIONS`` the protocol falls back to ``BASE_WEIGHT = 1.0``,
    so anything below that floor is meaningless.
    """
    if target_weight <= 0.0:
        return 0.0
    if not (0.0 <= sybil_brier <= 1.0):
        raise ValueError(f"sybil_brier {sybil_brier!r} must be in [0, 1]")
    raw_max = 1.0 / (sybil_brier + _weights.EPSILON)
    if target_weight > raw_max:
        return _INFINITY_PREDICTIONS
    n = target_weight * (sybil_brier + _weights.EPSILON) * _weights.CONFIDENCE_THRESHOLD
    return max(float(_weights.MIN_PREDICTIONS), n)


# ---------------------------------------------------------------------------
# Combined summary — single function that produces a publication-grade report.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SecurityMargin:
    """Snapshot of the protocol's economic-security posture for a scenario.

    Aggregates the cheap-Sybil cost (``min_base_weight_sybils``) and the
    earned-calibration ceiling (``max_attainable_sybil_weight``) into a
    single record suitable for direct display.
    """

    baseline_decision: DecisionLiteral
    baseline_probability: float
    target_decision: DecisionLiteral
    min_base_weight_sybils: float | int
    min_total_sybil_weight: float
    is_feasible_by_count: bool
    base_rate_assumed: float
    max_attainable_sybil_weight: float
    predictions_to_match_oracle: float
    notes: str = ""


def protocol_security_margin(
    scenario: AttackScenario,
    base_rate: float = 0.5,
    oracle_brier: float = 0.10,
) -> SecurityMargin:
    """Build a ``SecurityMargin`` for ``scenario`` against the cheap-Sybil
    attack model and the earned-calibration model.

    ``oracle_brier`` is the Brier score we treat as "oracle-tier" — agents
    at or below this Brier dominate the consensus. Default ``0.10`` matches
    the design-doc target for the best calibrated agents.
    """
    flip = min_weight_to_flip(scenario)
    ceiling = max_calibration_weight_constant_voter(base_rate)
    oracle_weight = _weights.compute_weight(
        oracle_brier, _weights.CONFIDENCE_THRESHOLD
    )
    predictions_to_match_oracle = sybil_break_even_predictions(
        target_weight=oracle_weight, sybil_brier=base_rate * (1.0 - base_rate)
    )

    return SecurityMargin(
        baseline_decision=flip.baseline_decision,
        baseline_probability=flip.baseline_probability,
        target_decision=scenario.target_decision,
        min_base_weight_sybils=flip.min_base_weight_sybils,
        min_total_sybil_weight=flip.min_total_sybil_weight,
        is_feasible_by_count=flip.is_feasible,
        base_rate_assumed=base_rate,
        max_attainable_sybil_weight=ceiling,
        predictions_to_match_oracle=predictions_to_match_oracle,
        notes=flip.notes,
    )


# ---------------------------------------------------------------------------
# Pretty-printing — keeps CLIs out of the math module while staying nearby.
# ---------------------------------------------------------------------------


def format_margin_text(margin: SecurityMargin) -> str:
    """Plain-text summary of a ``SecurityMargin`` for CLI output."""
    if margin.is_feasible_by_count:
        count_repr = (
            f"{int(margin.min_base_weight_sybils)} base-weight Sybils"
            if margin.min_base_weight_sybils != math.inf
            else "∞ (infeasible)"
        )
        weight_repr = f"{margin.min_total_sybil_weight:.3f} units of Sybil weight"
    else:
        count_repr = "∞ (infeasible at any count)"
        weight_repr = "∞"

    lines = [
        f"Baseline:        {margin.baseline_decision} @ p={margin.baseline_probability:.3f}",
        f"Target:          {margin.target_decision}",
        f"Cheap-Sybil cost: {count_repr}",
        f"                  ({weight_repr})",
        f"Base rate:       {margin.base_rate_assumed:.2f}",
        f"Max Sybil weight (constant voter, n→∞): "
        f"{margin.max_attainable_sybil_weight:.3f}",
        (
            f"Predictions to match oracle weight: "
            f"{margin.predictions_to_match_oracle:.0f}"
            if margin.predictions_to_match_oracle != _INFINITY_PREDICTIONS
            else "Cannot match oracle weight at any prediction count"
        ),
    ]
    if margin.notes:
        lines.append(f"Notes:           {margin.notes}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _SolveResult:
    is_feasible: bool
    min_total_sybil_weight: float
    notes: str = ""


def _default_attacker_vote(target_decision: DecisionLiteral) -> float:
    """The optimal Sybil vote against the threshold for each target.

    For YES, voting 1.0 is strictly optimal (largest push above threshold).
    For NO, 0.0. For DISPUTE we pick 0.5 — maximizes variance contribution
    in the equidistant case.
    """
    return {"YES": 1.0, "NO": 0.0, "DISPUTE": 0.5}[target_decision]


def _solve_threshold_flip(
    *,
    scenario: AttackScenario,
    attacker_vote: float,
    target_low: float,
    target_high: float,
    descending: bool,
) -> _SolveResult:
    """Solve for the minimum Sybil weight that achieves the target decision.

    The closed-form mean-crossing weight from

        W_s · (p_s − target) = target · W − A

    is *necessary* but not sufficient. At the exact mean-crossing point, the
    weight-aware variance is typically maximal — honest agents are clustered
    far from ``p_s``, and ``p_s`` is far from the new mean — which triggers
    the ``DISPUTE`` gate even though the mean alone would clear the threshold.

    The variance gate is itself a real Sybil-resistance feature: a naive
    attacker who only solves for the mean often pushes the protocol into
    DISPUTE rather than the target decision. The *true* cost of a flip
    accounts for both the mean and the variance — we increase ``W_s`` until
    the attacker dominates enough that weight-aware variance falls back
    below ``variance_threshold``.

    Algorithm: compute the closed-form mean-crossing weight (lower bound),
    simulate the consensus at that weight; if it already produces the target
    decision, done. Otherwise, binary-search upward to find the smallest
    ``W_s`` whose consensus decision equals the target.
    """
    raw_weights = [
        max(0.0, float(scenario.honest_weights.get(v.agent_id, scenario.default_weight)))
        for v in scenario.honest_votes
    ]
    W = sum(raw_weights)
    if W <= 0.0:
        return _SolveResult(
            is_feasible=False,
            min_total_sybil_weight=math.inf,
            notes=(
                "Honest weights sum to zero — protocol falls back to unweighted "
                "vote, and attacker can dominate with a single Sybil."
            ),
        )
    A = sum(w * v.probability for w, v in zip(raw_weights, scenario.honest_votes))

    # --- Closed-form mean-crossing lower bound. ---
    if descending:
        denom = target_high - attacker_vote
        numer = A - target_high * W
        target_decision: DecisionLiteral = "NO"
        if denom <= 0.0:
            return _SolveResult(
                is_feasible=False,
                min_total_sybil_weight=math.inf,
                notes=(
                    f"Attacker vote {attacker_vote:.3f} ≥ no_threshold "
                    f"{target_high:.3f}; cannot push consensus below threshold."
                ),
            )
    else:
        denom = attacker_vote - target_low
        numer = target_low * W - A
        target_decision = "YES"
        if denom <= 0.0:
            return _SolveResult(
                is_feasible=False,
                min_total_sybil_weight=math.inf,
                notes=(
                    f"Attacker vote {attacker_vote:.3f} ≤ yes_threshold "
                    f"{target_low:.3f}; cannot push consensus above threshold."
                ),
            )

    mean_crossing_lb = max(0.0, numer / denom)

    # --- Decision-aware search: bisect upward from the closed-form lower
    #     bound until the consensus decision is the target. ---
    def decision_at(w_s: float) -> str:
        return _simulate_with_sybil_mass(
            scenario, w_s, attacker_vote
        ).decision

    if mean_crossing_lb == 0.0:
        return _SolveResult(is_feasible=True, min_total_sybil_weight=0.0)

    # If the closed-form weight already produces the target decision (no
    # variance trap), we are done — variance is irrelevant for the protocol
    # at this attack volume.
    if decision_at(mean_crossing_lb) == target_decision:
        return _SolveResult(
            is_feasible=True, min_total_sybil_weight=mean_crossing_lb
        )

    # Otherwise, exponentially expand until decision == target, then bisect.
    lo = mean_crossing_lb
    hi = mean_crossing_lb
    for _ in range(80):
        hi = hi * 2.0 if hi > 0 else 1.0
        if decision_at(hi) == target_decision:
            break
    else:
        return _SolveResult(
            is_feasible=False,
            min_total_sybil_weight=math.inf,
            notes=(
                "Could not find any Sybil weight that satisfies both the mean "
                "and variance gates simultaneously — variance threshold is "
                "binding for this attacker vote."
            ),
        )

    for _ in range(60):
        mid = (lo + hi) / 2
        if decision_at(mid) == target_decision:
            hi = mid
        else:
            lo = mid

    notes = ""
    if hi > mean_crossing_lb * (1.0 + 1e-6):
        # Variance gate pushed the real cost above the closed-form bound.
        notes = (
            "Variance gate raises cost above the closed-form mean-crossing "
            f"bound ({mean_crossing_lb:.3f}) — the variance threshold makes "
            "naive Sybil attacks more expensive than the mean-only math "
            "suggests."
        )
    return _SolveResult(
        is_feasible=True, min_total_sybil_weight=hi, notes=notes
    )


def _simulate_with_sybil_mass(
    scenario: AttackScenario, total_sybil_weight: float, attacker_vote: float
) -> _consensus.ConsensusResult:
    """Replay the consensus engine with a single synthetic Sybil contribution
    representing the entire attacker stake. This is the ground-truth oracle
    for whether a given Sybil weight actually flips the protocol decision.
    """
    sybil_vote = _consensus.AgentVote(
        agent_id="__sybil_mass__",
        probability=attacker_vote,
        confidence=1.0,
    )
    weights_with_sybil = dict(scenario.honest_weights)
    weights_with_sybil["__sybil_mass__"] = total_sybil_weight
    return _consensus.aggregate_consensus(
        scenario.honest_votes + [sybil_vote],
        weights_with_sybil,
        yes_threshold=scenario.yes_threshold,
        no_threshold=scenario.no_threshold,
        variance_threshold=scenario.variance_threshold,
        default_weight=scenario.default_weight,
    )


def _solve_dispute(
    *, scenario: AttackScenario, attacker_vote: float
) -> _SolveResult:
    """Solve the dispute-injection problem.

    Two paths:
      (a) Drive the weighted-mean probability into the uncertainty band
          ``(no_threshold, yes_threshold)``.
      (b) Drive the weight-aware variance above ``variance_threshold``.

    We compute the minimum Sybil weight for each path and return the cheaper.
    The "mean" path uses the same closed form as ``_solve_threshold_flip``
    re-targeted to either endpoint of the band (whichever the attacker
    needs to cross).

    The "variance" path is monotonic in ``W_s`` (weight-aware variance
    increases when the attacker injects a fixed off-mean vote with growing
    weight share), so we solve numerically via bisection.
    """
    raw_weights = [
        max(0.0, float(scenario.honest_weights.get(v.agent_id, scenario.default_weight)))
        for v in scenario.honest_votes
    ]
    W = sum(raw_weights)
    A = sum(w * v.probability for w, v in zip(raw_weights, scenario.honest_votes))
    if W <= 0.0:
        return _SolveResult(
            is_feasible=False,
            min_total_sybil_weight=math.inf,
            notes="Honest weights sum to zero; dispute is the default.",
        )

    # --- Path (a): cross into the band. ---
    p_honest = A / W
    band_cost: float
    if scenario.no_threshold < p_honest < scenario.yes_threshold:
        band_cost = 0.0
    elif p_honest >= scenario.yes_threshold:
        # Need to push DOWN to yes_threshold. Attacker vote must be < target.
        denom = scenario.yes_threshold - attacker_vote
        if denom <= 0.0:
            band_cost = math.inf
        else:
            band_cost = max(
                0.0, (A - scenario.yes_threshold * W) / denom
            )
    else:
        # p_honest ≤ no_threshold; push UP to no_threshold.
        denom = attacker_vote - scenario.no_threshold
        if denom <= 0.0:
            band_cost = math.inf
        else:
            band_cost = max(
                0.0, (scenario.no_threshold * W - A) / denom
            )

    # --- Path (b): bisect on variance. ---
    variance_cost = _bisect_variance_cost(
        scenario=scenario,
        raw_weights=raw_weights,
        attacker_vote=attacker_vote,
    )

    candidates = [c for c in (band_cost, variance_cost) if c != math.inf]
    if not candidates:
        return _SolveResult(
            is_feasible=False,
            min_total_sybil_weight=math.inf,
            notes="Both dispute paths infeasible at this attacker_vote.",
        )

    chosen = min(candidates)
    notes = (
        "Cheapest dispute path: "
        + (
            "cross into uncertainty band"
            if chosen == band_cost and band_cost != math.inf
            else "inflate variance above threshold"
        )
    )
    return _SolveResult(is_feasible=True, min_total_sybil_weight=chosen, notes=notes)


def _bisect_variance_cost(
    *,
    scenario: AttackScenario,
    raw_weights: list[float],
    attacker_vote: float,
) -> float:
    """Bisect the minimum total Sybil weight that pushes weight-aware
    variance above ``variance_threshold``.

    The function ``W_s → variance(honest + Sybils with vote=attacker_vote,
    total weight W_s)`` is continuous and (for an off-mean attacker_vote)
    increases then decreases as ``W_s`` grows (the attacker eventually
    dominates and the variance falls again). We therefore probe a
    coarse grid first to find an interval crossing the threshold, then
    bisect within that interval.
    """
    target_var = scenario.variance_threshold
    if target_var <= 0.0:
        return 0.0

    def variance_at(w_s: float) -> float:
        total_w = sum(raw_weights) + w_s
        if total_w <= 0.0:
            return 0.0
        weights_norm = [w / total_w for w in raw_weights] + [w_s / total_w]
        probs = [v.probability for v in scenario.honest_votes] + [attacker_vote]
        mean = sum(w * p for w, p in zip(weights_norm, probs))
        return sum(w * (p - mean) ** 2 for w, p in zip(weights_norm, probs))

    # Coarse logarithmic scan to find an upper bound where variance >= target
    # (if it ever does).
    upper = math.inf
    grid: list[float] = []
    w_s = 0.001
    while w_s <= 1.0e6:
        grid.append(w_s)
        w_s *= 1.6
    for candidate in grid:
        if variance_at(candidate) >= target_var:
            upper = candidate
            break
    if upper == math.inf:
        return math.inf

    # Bisect between 0 and `upper`.
    lo, hi = 0.0, upper
    for _ in range(60):
        mid = (lo + hi) / 2
        if variance_at(mid) >= target_var:
            hi = mid
        else:
            lo = mid
    return hi


def _check_unit_interval(name: str, value: float) -> None:
    if not (0.0 <= value <= 1.0):
        raise ValueError(f"{name} {value!r} must be in [0, 1]")


# ---------------------------------------------------------------------------
# Demo helpers for documentation / CLI.
# ---------------------------------------------------------------------------


def demo_scenario(
    target_decision: DecisionLiteral = "YES",
) -> AttackScenario:
    """A canonical scenario matching the README's demo run.

    Three honest agents from ``weights.mock_brier_history`` voting on a
    crypto question that currently resolves NO (consensus probability
    ≈ 0.16). The attacker wants the protocol to announce YES instead.
    """
    history = _weights.mock_brier_history()
    honest_weights = _weights.weights_from_history(history)

    votes = [
        _consensus.AgentVote(
            agent_id="agent-oracle",
            probability=0.10,
            confidence=0.85,
            reasoning="Carefully reviewed evidence: outcome unlikely.",
            research_strategy="conservative-finance",
        ),
        _consensus.AgentVote(
            agent_id="agent-reliable",
            probability=0.18,
            confidence=0.70,
            reasoning="Some uncertainty but most signals point NO.",
            research_strategy="balanced",
        ),
        _consensus.AgentVote(
            agent_id="agent-novice",
            probability=0.30,
            confidence=0.50,
            reasoning="Less confident, leaning NO.",
            research_strategy="generalist",
        ),
    ]
    return AttackScenario(
        honest_votes=votes,
        honest_weights=honest_weights,
        target_decision=target_decision,
    )
