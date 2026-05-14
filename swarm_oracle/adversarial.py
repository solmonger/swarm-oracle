"""Multi-attacker adversarial simulation for the Swarm Oracle protocol.

Extends :mod:`swarm_oracle.sybil` (single-attacker analysis) to three
classes of attack that hackathon / production blockchain reviewers ask
about most often:

1. **Collusion** — *k* Sybils with coordinated votes and weights. The
   protocol's linear weight aggregation gives a clean "Symmetric
   Collusion Lemma": coordinating *k* identical-vote Sybils is
   operationally equivalent to one Sybil at the summed weight. The
   interesting case is *asymmetric* collusion that splits votes to game
   the variance gate.

2. **Adaptive attacker** — an attacker who observes every honest vote
   before choosing :math:`p_a` and the weight split across colluders.
   This is the strongest non-bribery model. The closed-form mean-crossing
   bound from :mod:`sybil` already assumes optimal :math:`p_a`; the
   adaptive lever that's actually new here is *splitting* the attacker's
   weight across multiple Sybils with different votes to suppress the
   variance contribution.

3. **Bribery** — the attacker pays existing honest agents to misvote.
   Cost is linear in the number of flipped agents. Optimal strategy
   greedily flips the highest-weight honest agents first.

A fourth function :func:`compose_attacks` composes Sybils + bribery and
returns the lower-cost attack on a per-dollar basis.

All functions are pure (no I/O, no LLM calls) and mirror the on-chain
``CalibrationRegistry`` math. See ``docs/threat-model.md`` for the
writeup that consumes this module's outputs.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Literal

from . import consensus as _consensus
from . import sybil as _sybil
from . import weights as _weights

DecisionLiteral = Literal["YES", "NO", "DISPUTE"]

# ---------------------------------------------------------------------------
# Constants & sentinels
# ---------------------------------------------------------------------------

# Sentinel large weight used when an attack is already trivially feasible
# (e.g. honest swarm already produces the target decision).
_NO_ATTACK_NEEDED = 0.0
_INFEASIBLE = math.inf

# Default per-agent bribery cost in USD when the caller hasn't specified one.
# Derived from a back-of-envelope: a small validator's expected daily reward
# on Base Sepolia at the protocol's planned reward schedule is ~$25, so a
# one-time bribe of $250 (10x daily reward) is a reasonable lower bound for
# any rational honest agent. Used purely as a default for the demo; production
# threat models should plug in their own cost basis.
DEFAULT_BRIBERY_COST_USD = 250.0


# ---------------------------------------------------------------------------
# Data classes — public surface
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CollusionScenario:
    """Inputs for a coordinated-Sybil attack.

    Attributes:
        base: The single-attacker :class:`AttackScenario` describing the
            honest swarm and target decision.
        num_colluders: Number of Sybil agents the attacker controls
            (≥ 1). When 1, this degenerates to the single-Sybil case.
        coordinated_votes: Per-Sybil probability votes. Length must equal
            ``num_colluders``. If ``None``, every Sybil votes the
            target-optimal probability (1.0 for YES, 0.0 for NO, 0.5
            for DISPUTE — same as :mod:`sybil` defaults).
        coordinated_weights: Per-Sybil weights. Length must equal
            ``num_colluders``. If ``None``, every Sybil is given the
            base weight 1.0 (i.e. fresh registry entries).
    """

    base: _sybil.AttackScenario
    num_colluders: int
    coordinated_votes: list[float] | None = None
    coordinated_weights: list[float] | None = None

    def __post_init__(self) -> None:
        if self.num_colluders < 1:
            raise ValueError(
                f"num_colluders must be ≥ 1, got {self.num_colluders}"
            )
        if self.coordinated_votes is not None:
            if len(self.coordinated_votes) != self.num_colluders:
                raise ValueError(
                    f"coordinated_votes length {len(self.coordinated_votes)} "
                    f"≠ num_colluders {self.num_colluders}"
                )
            for v in self.coordinated_votes:
                if not (0.0 <= v <= 1.0):
                    raise ValueError(
                        f"coordinated vote {v!r} must be in [0, 1]"
                    )
        if self.coordinated_weights is not None:
            if len(self.coordinated_weights) != self.num_colluders:
                raise ValueError(
                    f"coordinated_weights length {len(self.coordinated_weights)} "
                    f"≠ num_colluders {self.num_colluders}"
                )
            for w in self.coordinated_weights:
                if w < 0.0:
                    raise ValueError(
                        f"coordinated weight {w!r} must be ≥ 0"
                    )


@dataclass(frozen=True)
class CollusionResult:
    """Outcome of a coordinated-Sybil attack.

    Attributes:
        success: True if the coordinated attack achieves the target
            decision under the current protocol parameters.
        achieved_decision: The decision the protocol actually announces
            given the colluders' votes and weights.
        achieved_probability: The weighted consensus probability after
            the colluders' votes are included.
        total_sybil_weight: Sum of all colluder weights.
        equivalent_single_sybil_weight: For comparison — the weight a
            single attacker with the same total weight and target-optimal
            vote would need. From :mod:`sybil` closed-form bound.
        notes: Human-readable explanation of why the attack succeeded or
            failed.
    """

    success: bool
    achieved_decision: DecisionLiteral
    achieved_probability: float
    total_sybil_weight: float
    equivalent_single_sybil_weight: float
    notes: str = ""


@dataclass(frozen=True)
class AdaptiveScenario:
    """Inputs for an adaptive-attacker analysis.

    The adaptive attacker sees every honest vote and weight before
    choosing both :math:`p_a` and the weight split across colluders.

    Attributes:
        base: Single-attacker scenario (honest swarm + target).
        num_sybils: Number of Sybils the adaptive attacker may register.
            Higher values give more freedom to game the variance gate.
        max_weight_per_sybil: Per-Sybil weight cap. Defaults to
            :data:`~swarm_oracle.weights.BASE_WEIGHT` (fresh registry
            entries). For a calibration-earned attacker, raise this and
            consult :func:`~swarm_oracle.sybil.sybil_break_even_predictions`
            to compute the prediction count needed.
    """

    base: _sybil.AttackScenario
    num_sybils: int = 1
    max_weight_per_sybil: float = _weights.BASE_WEIGHT

    def __post_init__(self) -> None:
        if self.num_sybils < 1:
            raise ValueError(
                f"num_sybils must be ≥ 1, got {self.num_sybils}"
            )
        if self.max_weight_per_sybil < 0.0:
            raise ValueError(
                f"max_weight_per_sybil must be ≥ 0, got "
                f"{self.max_weight_per_sybil}"
            )


@dataclass(frozen=True)
class AdaptiveResult:
    """Outcome of an adaptive-attacker analysis.

    Attributes:
        is_feasible: True if the adaptive attacker can flip the decision
            with weight ≤ ``num_sybils * max_weight_per_sybil``.
        min_total_weight: Smallest total Sybil weight that achieves the
            target. ``inf`` if infeasible at the given budget.
        optimal_strategy: Human-readable description of the best split
            found (e.g. ``"single Sybil voting 1.0 at weight 272.0"``).
        budget_total: ``num_sybils * max_weight_per_sybil`` — the budget
            the adaptive attacker had to work with.
        baseline_decision: Decision the honest swarm produces without
            the attacker.
        notes: Free-form notes (variance-gate engagement, edge cases).
    """

    is_feasible: bool
    min_total_weight: float
    optimal_strategy: str
    budget_total: float
    baseline_decision: DecisionLiteral
    notes: str = ""


@dataclass(frozen=True)
class BriberyScenario:
    """Inputs for a bribery-attack analysis.

    Attributes:
        base: Single-attacker scenario (honest swarm + target).
        cost_per_agent_usd: USD cost to flip each honest agent. The same
            cost applies regardless of agent weight (one-shot bribe).
        flipped_vote: The vote a bribed agent casts (1.0 for a YES
            target, 0.0 for NO, 0.5 for DISPUTE — defaults follow
            :mod:`sybil`).
    """

    base: _sybil.AttackScenario
    cost_per_agent_usd: float = DEFAULT_BRIBERY_COST_USD
    flipped_vote: float | None = None

    def __post_init__(self) -> None:
        if self.cost_per_agent_usd < 0.0:
            raise ValueError(
                f"cost_per_agent_usd must be ≥ 0, got "
                f"{self.cost_per_agent_usd}"
            )
        v = self.flipped_vote
        if v is not None and not (0.0 <= v <= 1.0):
            raise ValueError(f"flipped_vote {v!r} must be in [0, 1]")


@dataclass(frozen=True)
class BriberyResult:
    """Outcome of a bribery-attack analysis.

    Attributes:
        is_feasible: True if any number of agents flipped achieves the
            target. False only when even flipping every honest agent
            fails (e.g. variance gate locks the consensus).
        num_agents_flipped: Minimum count of honest agents that must be
            bribed to flip the decision. ``inf`` if infeasible.
        min_cost_usd: ``num_agents_flipped * cost_per_agent_usd``. ``inf``
            if infeasible.
        flipped_agent_ids: Ordered list of agent IDs that must be
            bribed, in the greedy descending-weight order the algorithm
            chose them.
        baseline_decision: Decision the honest swarm produces without
            any bribery.
        achieved_decision: Decision after the chosen agents are flipped.
        notes: Free-form notes.
    """

    is_feasible: bool
    num_agents_flipped: float | int
    min_cost_usd: float
    flipped_agent_ids: list[str]
    baseline_decision: DecisionLiteral
    achieved_decision: DecisionLiteral
    notes: str = ""


@dataclass(frozen=True)
class ComposedAttackResult:
    """Side-by-side comparison of attack vectors with a common cost basis.

    Attributes:
        sybil_cost_usd: Cost of the cheapest single-Sybil attack
            expressed in USD = ``min_base_weight_sybils * registry_cost_usd``.
        sybil_count: ``min_base_weight_sybils`` for reference.
        bribery_cost_usd: Cost of the cheapest bribery attack.
        bribery_agents_flipped: Number of honest agents the bribery
            attack flips.
        cheapest_vector: ``"sybil"`` or ``"bribery"`` — whichever costs
            less. If both infeasible: ``"infeasible"``.
        cheapest_cost_usd: Minimum of the two finite costs (``inf`` if
            both infeasible).
        notes: Human-readable summary.
    """

    sybil_cost_usd: float
    sybil_count: float | int
    bribery_cost_usd: float
    bribery_agents_flipped: float | int
    cheapest_vector: str
    cheapest_cost_usd: float
    notes: str = ""


# ---------------------------------------------------------------------------
# Public API — collusion
# ---------------------------------------------------------------------------


def simulate_collusion(scenario: CollusionScenario) -> CollusionResult:
    """Simulate *k* colluding Sybils with explicit per-Sybil votes/weights.

    Replays the consensus engine with the honest votes plus the *k*
    Sybil votes. Returns whether the resulting decision matches the
    attacker's target.

    The ``equivalent_single_sybil_weight`` field lets callers verify the
    *Symmetric Collusion Lemma*: when all colluders vote the same
    probability, the result is identical to one Sybil at the summed
    weight.
    """
    base = scenario.base

    # Resolve defaults
    votes = scenario.coordinated_votes
    if votes is None:
        default_p = _default_attacker_vote(base.target_decision)
        votes = [default_p] * scenario.num_colluders

    raw_weights = scenario.coordinated_weights
    if raw_weights is None:
        raw_weights = [_weights.BASE_WEIGHT] * scenario.num_colluders

    # Build the augmented vote/weight maps for consensus
    augmented_votes = list(base.honest_votes)
    augmented_weights = dict(base.honest_weights)
    for i in range(scenario.num_colluders):
        sybil_id = f"__colluder_{i}__"
        augmented_votes.append(
            _consensus.AgentVote(
                agent_id=sybil_id,
                probability=votes[i],
                confidence=1.0,
            )
        )
        augmented_weights[sybil_id] = raw_weights[i]

    result = _consensus.aggregate_consensus(
        augmented_votes,
        augmented_weights,
        yes_threshold=base.yes_threshold,
        no_threshold=base.no_threshold,
        variance_threshold=base.variance_threshold,
        default_weight=base.default_weight,
    )

    total_weight = sum(raw_weights)

    # Compute equivalent single-Sybil weight for the comparison field.
    # Only meaningful when all colluders vote the same probability; we
    # use the mean of votes as a "representative" single-Sybil vote.
    if votes:
        rep_vote = sum(votes) / len(votes)
        all_same = all(abs(v - votes[0]) < 1e-9 for v in votes)
        if all_same and total_weight > 0.0:
            single_scenario = _replace_attacker_vote(base, rep_vote)
            single = _sybil.min_weight_to_flip(single_scenario)
            equivalent = single.min_total_sybil_weight
        else:
            equivalent = math.nan
    else:
        equivalent = math.nan

    success = result.decision == base.target_decision

    if success:
        notes = (
            f"Coordinated {scenario.num_colluders} Sybils flipped to "
            f"{result.decision} at total weight {total_weight:.3f}."
        )
    else:
        notes = (
            f"Coordination achieved {result.decision} (p={result.probability:.3f}), "
            f"not target {base.target_decision}. Variance={result.variance:.3f}."
        )

    return CollusionResult(
        success=success,
        achieved_decision=result.decision,  # type: ignore[arg-type]
        achieved_probability=result.probability,
        total_sybil_weight=total_weight,
        equivalent_single_sybil_weight=equivalent,
        notes=notes,
    )


def collusion_equivalence_check(
    base: _sybil.AttackScenario,
    num_colluders: int,
    total_weight: float,
) -> tuple[CollusionResult, _sybil.AttackResult]:
    """Verify the Symmetric Collusion Lemma empirically.

    Returns a (collusion, single-attacker) pair. The lemma says: if all
    *k* colluders vote target-optimal and total weight equals the
    single-attacker bound, the consensus decisions match.
    """
    p_attack = _default_attacker_vote(base.target_decision)
    per_sybil = total_weight / num_colluders if num_colluders > 0 else 0.0
    collusion = simulate_collusion(
        CollusionScenario(
            base=base,
            num_colluders=num_colluders,
            coordinated_votes=[p_attack] * num_colluders,
            coordinated_weights=[per_sybil] * num_colluders,
        )
    )
    single = _sybil.min_weight_to_flip(base)
    return collusion, single


# ---------------------------------------------------------------------------
# Public API — adaptive attacker
# ---------------------------------------------------------------------------


def min_adaptive_weight(scenario: AdaptiveScenario) -> AdaptiveResult:
    """Minimum total weight for an attacker that splits across ``num_sybils``.

    The optimisation: pick a per-Sybil vote :math:`p_i \\in [0,1]` and a
    per-Sybil weight :math:`w_i \\le` ``max_weight_per_sybil`` to flip
    the decision with smallest :math:`\\sum w_i`.

    *Theorem* (concentrated-vote optimality at the mean stage): for the
    YES/NO targets, the mean-crossing bound is monotone non-increasing
    in the attacker vote — voting the threshold-extreme is strictly
    optimal at the mean stage. Therefore the only reason an adaptive
    attacker would split votes is to *suppress variance* and avoid the
    DISPUTE gate.

    Algorithm:
      1. Compute the single-attacker bound (concentrated-vote
         baseline).
      2. If the concentrated attack doesn't trigger the variance gate
         (i.e. it cleanly flips), return the single-attacker bound.
      3. Otherwise, simulate a *spread* strategy: half the colluders at
         the target-extreme, half at a vote close to the honest
         weighted mean — this drops variance because the Sybils now
         straddle the honest cluster.
      4. Return the smaller of the two costs.

    Budget enforcement: if the smallest cost exceeds
    ``num_sybils * max_weight_per_sybil``, the attack is reported
    infeasible at the given budget.
    """
    base = scenario.base
    budget_total = scenario.num_sybils * scenario.max_weight_per_sybil

    baseline = _sybil.baseline_consensus(base)
    if baseline.decision == base.target_decision:
        return AdaptiveResult(
            is_feasible=True,
            min_total_weight=0.0,
            optimal_strategy="no attack needed — honest swarm already at target",
            budget_total=budget_total,
            baseline_decision=baseline.decision,  # type: ignore[arg-type]
            notes="Honest swarm already produces target decision.",
        )

    # --- Strategy A: concentrated extreme vote (the sybil.min_weight_to_flip
    # answer). This is the closed-form optimal at the mean stage.
    concentrated = _sybil.min_weight_to_flip(base)

    candidates: list[tuple[float, str, str]] = []
    if concentrated.is_feasible:
        candidates.append(
            (
                concentrated.min_total_sybil_weight,
                f"concentrated vote {concentrated.attacker_vote_used:.2f} "
                f"at total weight {concentrated.min_total_sybil_weight:.3f}",
                concentrated.notes,
            )
        )

    # --- Strategy B: spread across two clusters to neutralise the variance
    # gate. Only meaningful when num_sybils ≥ 2 and target is YES/NO.
    if scenario.num_sybils >= 2 and base.target_decision in ("YES", "NO"):
        honest_mean = _honest_weighted_mean(base)
        # Half push toward the threshold, half straddle the honest cluster.
        if base.target_decision == "YES":
            spread_a, spread_b = 1.0, max(0.0, min(1.0, honest_mean))
        else:
            spread_a, spread_b = 0.0, max(0.0, min(1.0, honest_mean))
        spread_cost = _bisect_spread_weight(
            base=base,
            num_sybils=scenario.num_sybils,
            vote_a=spread_a,
            vote_b=spread_b,
        )
        if spread_cost != _INFEASIBLE:
            candidates.append(
                (
                    spread_cost,
                    f"split {scenario.num_sybils} Sybils across votes "
                    f"({spread_a:.2f}, {spread_b:.2f}) at total weight "
                    f"{spread_cost:.3f}",
                    "Spread strategy chosen to suppress variance gate.",
                )
            )

    if not candidates:
        return AdaptiveResult(
            is_feasible=False,
            min_total_weight=_INFEASIBLE,
            optimal_strategy="no strategy feasible",
            budget_total=budget_total,
            baseline_decision=baseline.decision,  # type: ignore[arg-type]
            notes="No adaptive attack found — variance gate locks decision.",
        )

    best_cost, best_desc, best_notes = min(candidates, key=lambda c: c[0])
    feasible_at_budget = best_cost <= budget_total + 1e-9
    return AdaptiveResult(
        is_feasible=feasible_at_budget,
        min_total_weight=best_cost,
        optimal_strategy=best_desc,
        budget_total=budget_total,
        baseline_decision=baseline.decision,  # type: ignore[arg-type]
        notes=best_notes
        + (
            ""
            if feasible_at_budget
            else f" Exceeds budget {budget_total:.3f}."
        ),
    )


# ---------------------------------------------------------------------------
# Public API — bribery
# ---------------------------------------------------------------------------


def min_bribery_cost(scenario: BriberyScenario) -> BriberyResult:
    """Minimum bribery cost to flip the decision.

    Greedy algorithm: sort honest agents by weight descending; flip them
    one at a time (replacing their vote with ``flipped_vote``) until the
    consensus decision matches ``target_decision`` or all agents are
    exhausted.

    *Optimality argument*: at every step, flipping a higher-weight agent
    moves the weighted mean further in the attacker's direction than
    flipping any lower-weight agent would. Since bribery cost is constant
    per flip, greedy-by-weight dominates every other ordering.
    """
    base = scenario.base
    p_flip = (
        scenario.flipped_vote
        if scenario.flipped_vote is not None
        else _default_attacker_vote(base.target_decision)
    )

    baseline = _sybil.baseline_consensus(base)
    if baseline.decision == base.target_decision:
        return BriberyResult(
            is_feasible=True,
            num_agents_flipped=0,
            min_cost_usd=0.0,
            flipped_agent_ids=[],
            baseline_decision=baseline.decision,  # type: ignore[arg-type]
            achieved_decision=baseline.decision,  # type: ignore[arg-type]
            notes="Honest swarm already produces target decision; no bribery needed.",
        )

    # Sort honest agents by weight descending; ties broken by agent_id for
    # determinism.
    honest_agents = sorted(
        base.honest_votes,
        key=lambda v: (
            -float(base.honest_weights.get(v.agent_id, base.default_weight)),
            v.agent_id,
        ),
    )

    flipped: list[str] = []
    for i, victim in enumerate(honest_agents, start=1):
        new_votes = [
            _consensus.AgentVote(
                agent_id=v.agent_id,
                probability=p_flip if v.agent_id in flipped + [victim.agent_id]
                else v.probability,
                confidence=v.confidence,
            )
            for v in base.honest_votes
        ]
        # Try the consensus with victim flipped too
        trial_flipped = flipped + [victim.agent_id]
        trial_votes = [
            _consensus.AgentVote(
                agent_id=v.agent_id,
                probability=p_flip if v.agent_id in trial_flipped else v.probability,
                confidence=v.confidence,
            )
            for v in base.honest_votes
        ]
        trial_result = _consensus.aggregate_consensus(
            trial_votes,
            base.honest_weights,
            yes_threshold=base.yes_threshold,
            no_threshold=base.no_threshold,
            variance_threshold=base.variance_threshold,
            default_weight=base.default_weight,
        )
        flipped.append(victim.agent_id)
        if trial_result.decision == base.target_decision:
            return BriberyResult(
                is_feasible=True,
                num_agents_flipped=i,
                min_cost_usd=i * scenario.cost_per_agent_usd,
                flipped_agent_ids=flipped,
                baseline_decision=baseline.decision,  # type: ignore[arg-type]
                achieved_decision=trial_result.decision,  # type: ignore[arg-type]
                notes=(
                    f"Greedy bribery: flipped {i} highest-weight agents to "
                    f"vote={p_flip:.2f}."
                ),
            )

    # All agents flipped, still didn't reach target.
    final = _consensus.aggregate_consensus(
        [
            _consensus.AgentVote(
                agent_id=v.agent_id,
                probability=p_flip,
                confidence=v.confidence,
            )
            for v in base.honest_votes
        ],
        base.honest_weights,
        yes_threshold=base.yes_threshold,
        no_threshold=base.no_threshold,
        variance_threshold=base.variance_threshold,
        default_weight=base.default_weight,
    )
    return BriberyResult(
        is_feasible=False,
        num_agents_flipped=_INFEASIBLE,
        min_cost_usd=_INFEASIBLE,
        flipped_agent_ids=flipped,
        baseline_decision=baseline.decision,  # type: ignore[arg-type]
        achieved_decision=final.decision,  # type: ignore[arg-type]
        notes=(
            f"Even flipping every honest agent to vote={p_flip:.2f} "
            f"produces {final.decision} (p={final.probability:.3f}, "
            f"var={final.variance:.3f}); attacker_vote may be on the wrong "
            "side of the threshold."
        ),
    )


# ---------------------------------------------------------------------------
# Public API — composed comparison
# ---------------------------------------------------------------------------


def compose_attacks(
    base: _sybil.AttackScenario,
    registry_cost_usd: float = 5.0,
    bribery_cost_usd: float = DEFAULT_BRIBERY_COST_USD,
) -> ComposedAttackResult:
    """Compare Sybil and bribery attacks on a common USD cost basis.

    ``registry_cost_usd`` is the cost to register one Sybil agent
    (gas + small staking deposit). ``bribery_cost_usd`` is the cost
    to flip one honest agent.

    Returns the cheaper option with diagnostics for both.
    """
    sybil_result = _sybil.min_weight_to_flip(base)
    sybil_cost: float
    sybil_count: float | int
    if sybil_result.is_feasible and sybil_result.min_base_weight_sybils != math.inf:
        sybil_count = sybil_result.min_base_weight_sybils
        sybil_cost = float(sybil_count) * registry_cost_usd
    else:
        sybil_count = _INFEASIBLE
        sybil_cost = _INFEASIBLE

    bribery_result = min_bribery_cost(
        BriberyScenario(base=base, cost_per_agent_usd=bribery_cost_usd)
    )
    bribery_cost = (
        float(bribery_result.min_cost_usd)
        if bribery_result.is_feasible
        else _INFEASIBLE
    )
    bribery_agents = bribery_result.num_agents_flipped

    if sybil_cost == _INFEASIBLE and bribery_cost == _INFEASIBLE:
        cheapest_vector = "infeasible"
        cheapest_cost = _INFEASIBLE
        notes = "Neither Sybil nor bribery feasible under given parameters."
    elif sybil_cost <= bribery_cost:
        cheapest_vector = "sybil"
        cheapest_cost = sybil_cost
        if bribery_cost == _INFEASIBLE:
            notes = (
                f"Sybil is the only feasible vector at ${sybil_cost:,.2f}."
            )
        else:
            notes = (
                f"Sybil cheaper than bribery (${sybil_cost:,.2f} vs "
                f"${bribery_cost:,.2f})."
            )
    else:
        cheapest_vector = "bribery"
        cheapest_cost = bribery_cost
        if sybil_cost == _INFEASIBLE:
            notes = (
                f"Bribery is the only feasible vector at ${bribery_cost:,.2f}."
            )
        else:
            notes = (
                f"Bribery cheaper than Sybil (${bribery_cost:,.2f} vs "
                f"${sybil_cost:,.2f})."
            )

    return ComposedAttackResult(
        sybil_cost_usd=sybil_cost,
        sybil_count=sybil_count,
        bribery_cost_usd=bribery_cost,
        bribery_agents_flipped=bribery_agents,
        cheapest_vector=cheapest_vector,
        cheapest_cost_usd=cheapest_cost,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Pretty-printing
# ---------------------------------------------------------------------------


def format_composed_text(composed: ComposedAttackResult) -> str:
    """Plain-text summary of a :class:`ComposedAttackResult` for CLI output."""
    def _fmt(x: float, prefix: str = "$") -> str:
        if x == _INFEASIBLE:
            return "∞ (infeasible)"
        return f"{prefix}{x:,.2f}"

    lines = [
        "--- Attack vector comparison ---",
        f"Sybil cost:    {_fmt(composed.sybil_cost_usd)}"
        + (
            f"  ({int(composed.sybil_count)} Sybils registered)"
            if composed.sybil_count not in (math.inf, math.nan)
            else ""
        ),
        f"Bribery cost:  {_fmt(composed.bribery_cost_usd)}"
        + (
            f"  ({int(composed.bribery_agents_flipped)} honest agents flipped)"
            if composed.bribery_agents_flipped not in (math.inf, math.nan)
            else ""
        ),
        f"Cheapest:      {composed.cheapest_vector}",
        f"Cheapest cost: {_fmt(composed.cheapest_cost_usd)}",
    ]
    if composed.notes:
        lines.append(f"Notes:         {composed.notes}")
    return "\n".join(lines)


def format_collusion_text(result: CollusionResult) -> str:
    """Plain-text summary of a :class:`CollusionResult`."""
    lines = [
        "--- Collusion result ---",
        f"Total Sybil weight:           {result.total_sybil_weight:.3f}",
        f"Equivalent single-Sybil bound: "
        + (
            f"{result.equivalent_single_sybil_weight:.3f}"
            if not math.isnan(result.equivalent_single_sybil_weight)
            else "n/a (asymmetric collusion)"
        ),
        f"Achieved decision:             {result.achieved_decision} "
        f"(p={result.achieved_probability:.3f})",
        f"Attack succeeded:              {'YES' if result.success else 'NO'}",
    ]
    if result.notes:
        lines.append(f"Notes:                         {result.notes}")
    return "\n".join(lines)


def format_adaptive_text(result: AdaptiveResult) -> str:
    """Plain-text summary of an :class:`AdaptiveResult`."""
    lines = [
        "--- Adaptive attacker result ---",
        f"Budget total weight:  {result.budget_total:.3f}",
        f"Min weight to flip:   "
        + (
            "∞ (infeasible)"
            if result.min_total_weight == _INFEASIBLE
            else f"{result.min_total_weight:.3f}"
        ),
        f"Feasible at budget:   {'YES' if result.is_feasible else 'NO'}",
        f"Optimal strategy:     {result.optimal_strategy}",
    ]
    if result.notes:
        lines.append(f"Notes:                {result.notes}")
    return "\n".join(lines)


def format_bribery_text(result: BriberyResult) -> str:
    """Plain-text summary of a :class:`BriberyResult`."""
    def _fmt_int(x: float | int) -> str:
        if x == _INFEASIBLE:
            return "∞"
        return str(int(x))

    lines = [
        "--- Bribery result ---",
        f"Baseline decision:   {result.baseline_decision}",
        f"Agents to flip:      {_fmt_int(result.num_agents_flipped)}",
        f"Total cost (USD):    "
        + (
            "∞ (infeasible)"
            if result.min_cost_usd == _INFEASIBLE
            else f"${result.min_cost_usd:,.2f}"
        ),
        f"Achieved decision:   {result.achieved_decision}",
        f"Flipped agent IDs:   "
        + (
            ", ".join(result.flipped_agent_ids)
            if result.flipped_agent_ids
            else "(none)"
        ),
    ]
    if result.notes:
        lines.append(f"Notes:               {result.notes}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Demo helpers
# ---------------------------------------------------------------------------


def demo_collusion_scenario(
    num_colluders: int = 3,
    target_decision: DecisionLiteral = "YES",
) -> CollusionScenario:
    """Canonical collusion scenario: 3 colluders voting target-optimal."""
    base = _sybil.demo_scenario(target_decision)
    return CollusionScenario(base=base, num_colluders=num_colluders)


def demo_adaptive_scenario(
    num_sybils: int = 4,
    target_decision: DecisionLiteral = "YES",
) -> AdaptiveScenario:
    """Canonical adaptive scenario: 4 Sybils, base weight each."""
    base = _sybil.demo_scenario(target_decision)
    return AdaptiveScenario(
        base=base,
        num_sybils=num_sybils,
        max_weight_per_sybil=100.0,  # generous budget to test the search
    )


def demo_bribery_scenario(
    target_decision: DecisionLiteral = "YES",
    cost_per_agent_usd: float = DEFAULT_BRIBERY_COST_USD,
) -> BriberyScenario:
    """Canonical bribery scenario for the docs / demo CLI."""
    base = _sybil.demo_scenario(target_decision)
    return BriberyScenario(base=base, cost_per_agent_usd=cost_per_agent_usd)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _default_attacker_vote(target_decision: DecisionLiteral) -> float:
    return {"YES": 1.0, "NO": 0.0, "DISPUTE": 0.5}[target_decision]


def _replace_attacker_vote(
    base: _sybil.AttackScenario, new_vote: float
) -> _sybil.AttackScenario:
    """Return a copy of ``base`` with ``attacker_vote`` overridden."""
    return _sybil.AttackScenario(
        honest_votes=base.honest_votes,
        honest_weights=base.honest_weights,
        target_decision=base.target_decision,
        attacker_vote=new_vote,
        yes_threshold=base.yes_threshold,
        no_threshold=base.no_threshold,
        variance_threshold=base.variance_threshold,
        default_weight=base.default_weight,
    )


def _honest_weighted_mean(base: _sybil.AttackScenario) -> float:
    """Compute the weighted mean of honest votes for ``base``."""
    raw_weights = [
        max(0.0, float(base.honest_weights.get(v.agent_id, base.default_weight)))
        for v in base.honest_votes
    ]
    total = sum(raw_weights)
    if total <= 0.0:
        return 0.5
    return sum(w * v.probability for w, v in zip(raw_weights, base.honest_votes)) / total


def _bisect_spread_weight(
    *,
    base: _sybil.AttackScenario,
    num_sybils: int,
    vote_a: float,
    vote_b: float,
) -> float:
    """Bisect the minimum total weight for a ``vote_a`` / ``vote_b`` split.

    Half the Sybils vote ``vote_a``, half vote ``vote_b``, equal weight
    each. Returns the smallest total weight that flips the decision, or
    :data:`_INFEASIBLE`.
    """
    n_a = num_sybils // 2
    n_b = num_sybils - n_a

    def decision_at(total: float) -> str:
        if total <= 0.0:
            return _sybil.baseline_consensus(base).decision
        per_sybil = total / num_sybils
        weights = [per_sybil] * num_sybils
        votes = [vote_a] * n_a + [vote_b] * n_b
        augmented_votes = list(base.honest_votes)
        augmented_weights = dict(base.honest_weights)
        for i, (p, w) in enumerate(zip(votes, weights)):
            sid = f"__spread_{i}__"
            augmented_votes.append(
                _consensus.AgentVote(agent_id=sid, probability=p, confidence=1.0)
            )
            augmented_weights[sid] = w
        result = _consensus.aggregate_consensus(
            augmented_votes,
            augmented_weights,
            yes_threshold=base.yes_threshold,
            no_threshold=base.no_threshold,
            variance_threshold=base.variance_threshold,
            default_weight=base.default_weight,
        )
        return result.decision

    target = base.target_decision

    # Find an upper bound where the spread strategy flips.
    upper = 1.0
    for _ in range(80):
        if decision_at(upper) == target:
            break
        upper *= 2.0
    else:
        return _INFEASIBLE

    lo, hi = 0.0, upper
    for _ in range(60):
        mid = (lo + hi) / 2
        if decision_at(mid) == target:
            hi = mid
        else:
            lo = mid
    return hi


# ---------------------------------------------------------------------------
# Public surface advertised for tooling / docs
# ---------------------------------------------------------------------------

__all__ = [
    # Scenarios
    "CollusionScenario",
    "AdaptiveScenario",
    "BriberyScenario",
    # Results
    "CollusionResult",
    "AdaptiveResult",
    "BriberyResult",
    "ComposedAttackResult",
    # Analysis functions
    "simulate_collusion",
    "collusion_equivalence_check",
    "min_adaptive_weight",
    "min_bribery_cost",
    "compose_attacks",
    # Formatters
    "format_collusion_text",
    "format_adaptive_text",
    "format_bribery_text",
    "format_composed_text",
    # Demos
    "demo_collusion_scenario",
    "demo_adaptive_scenario",
    "demo_bribery_scenario",
    # Constants
    "DEFAULT_BRIBERY_COST_USD",
]
