"""Unit tests for :mod:`swarm_oracle.adversarial`.

Covers the three attack vectors (collusion, adaptive, bribery), the
composed-attack comparison, and the pretty-printing helpers. Numbers
in this file are the source of truth for ``docs/threat-model.md``.
"""
from __future__ import annotations

import math

import pytest

from swarm_oracle import adversarial as adv
from swarm_oracle import consensus, sybil, weights


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_base_scenario(
    target: adv.DecisionLiteral = "YES",
) -> sybil.AttackScenario:
    """Build the canonical 3-honest-agent scenario used across tests."""
    return sybil.demo_scenario(target)


def _make_yes_already_winning() -> sybil.AttackScenario:
    """A scenario where honest swarm already produces YES — useful for
    short-circuit edge cases."""
    votes = [
        consensus.AgentVote(agent_id="h1", probability=0.95, confidence=0.9),
        consensus.AgentVote(agent_id="h2", probability=0.92, confidence=0.9),
        consensus.AgentVote(agent_id="h3", probability=0.96, confidence=0.9),
    ]
    return sybil.AttackScenario(
        honest_votes=votes,
        honest_weights={"h1": 5.0, "h2": 4.0, "h3": 3.0},
        target_decision="YES",
    )


# ---------------------------------------------------------------------------
# CollusionScenario validation
# ---------------------------------------------------------------------------


class TestCollusionScenarioValidation:
    def test_default_construction(self) -> None:
        scen = adv.CollusionScenario(
            base=_make_base_scenario(), num_colluders=3
        )
        assert scen.num_colluders == 3
        assert scen.coordinated_votes is None
        assert scen.coordinated_weights is None

    def test_rejects_zero_colluders(self) -> None:
        with pytest.raises(ValueError, match="num_colluders must be"):
            adv.CollusionScenario(base=_make_base_scenario(), num_colluders=0)

    def test_rejects_negative_colluders(self) -> None:
        with pytest.raises(ValueError, match="num_colluders must be"):
            adv.CollusionScenario(base=_make_base_scenario(), num_colluders=-1)

    def test_rejects_mismatched_votes(self) -> None:
        with pytest.raises(ValueError, match="coordinated_votes length"):
            adv.CollusionScenario(
                base=_make_base_scenario(),
                num_colluders=3,
                coordinated_votes=[1.0, 1.0],
            )

    def test_rejects_mismatched_weights(self) -> None:
        with pytest.raises(ValueError, match="coordinated_weights length"):
            adv.CollusionScenario(
                base=_make_base_scenario(),
                num_colluders=2,
                coordinated_weights=[1.0, 2.0, 3.0],
            )

    def test_rejects_out_of_range_vote(self) -> None:
        with pytest.raises(ValueError, match="coordinated vote"):
            adv.CollusionScenario(
                base=_make_base_scenario(),
                num_colluders=2,
                coordinated_votes=[1.0, 1.5],
            )

    def test_rejects_negative_weight(self) -> None:
        with pytest.raises(ValueError, match="coordinated weight"):
            adv.CollusionScenario(
                base=_make_base_scenario(),
                num_colluders=2,
                coordinated_weights=[1.0, -0.5],
            )


# ---------------------------------------------------------------------------
# Collusion simulation
# ---------------------------------------------------------------------------


class TestSimulateCollusion:
    def test_small_collusion_fails_to_flip(self) -> None:
        """Three colluders at base weight 1.0 each cannot flip a swarm
        whose honest weights are much higher."""
        result = adv.simulate_collusion(
            adv.CollusionScenario(base=_make_base_scenario(), num_colluders=3)
        )
        assert result.success is False
        # Achieved decision should not be the YES target.
        assert result.achieved_decision != "YES"
        assert result.total_sybil_weight == pytest.approx(3.0)

    def test_large_collusion_can_flip(self) -> None:
        """Enough Sybils at sufficient per-Sybil weight can flip YES."""
        result = adv.simulate_collusion(
            adv.CollusionScenario(
                base=_make_base_scenario(),
                num_colluders=100,
                coordinated_votes=[1.0] * 100,
                coordinated_weights=[5.0] * 100,
            )
        )
        assert result.success is True
        assert result.achieved_decision == "YES"
        assert result.total_sybil_weight == pytest.approx(500.0)

    def test_symmetric_collusion_lemma(self) -> None:
        """Symmetric Collusion Lemma: k Sybils all voting same probability
        with summed weight W produces same decision as 1 Sybil at weight W.

        Uses ``1.01 × bound`` rather than the exact bound: at the exact
        threshold ``std == variance_threshold`` (both 0.20 for the demo
        scenario), floating-point summation order can tip the comparison
        either way (summing 20 small ``(13.6/T) × Δ²`` terms vs one
        ``(272/T) × Δ²`` term produces identical mathematics but tiny
        rounding differences). Above the threshold by 1%, every split
        succeeds — confirming the lemma.
        """
        base = _make_base_scenario()
        single = sybil.min_weight_to_flip(base)
        assert single.is_feasible
        total_w = single.min_total_sybil_weight * 1.01  # epsilon above bound

        for k in (1, 2, 5, 20):
            result = adv.simulate_collusion(
                adv.CollusionScenario(
                    base=base,
                    num_colluders=k,
                    coordinated_votes=[1.0] * k,
                    coordinated_weights=[total_w / k] * k,
                )
            )
            assert result.success is True, f"k={k} failed lemma"
            # Equivalent single-Sybil weight matches single-attacker bound
            assert result.equivalent_single_sybil_weight == pytest.approx(
                single.min_total_sybil_weight, rel=1e-6
            )

    def test_collusion_below_bound_fails(self) -> None:
        """Just below the single-attacker bound, collusion at same total
        weight also fails — consistent with the Symmetric Collusion Lemma."""
        base = _make_base_scenario()
        single = sybil.min_weight_to_flip(base)
        # 1% under the threshold
        total_w = single.min_total_sybil_weight * 0.99

        result = adv.simulate_collusion(
            adv.CollusionScenario(
                base=base,
                num_colluders=5,
                coordinated_votes=[1.0] * 5,
                coordinated_weights=[total_w / 5] * 5,
            )
        )
        assert result.success is False

    def test_collusion_short_circuit_when_already_target(self) -> None:
        """If honest swarm already at target, even one Sybil counts as
        success without doing real work."""
        result = adv.simulate_collusion(
            adv.CollusionScenario(
                base=_make_yes_already_winning(),
                num_colluders=1,
            )
        )
        assert result.success is True
        assert result.achieved_decision == "YES"

    def test_asymmetric_collusion_records_nan_equivalence(self) -> None:
        """When colluders vote different probabilities, the
        equivalent_single_sybil_weight field is NaN (no single-vote
        equivalent exists)."""
        result = adv.simulate_collusion(
            adv.CollusionScenario(
                base=_make_base_scenario(),
                num_colluders=2,
                coordinated_votes=[0.9, 0.6],
                coordinated_weights=[10.0, 10.0],
            )
        )
        assert math.isnan(result.equivalent_single_sybil_weight)

    def test_collusion_notes_describe_outcome(self) -> None:
        result_success = adv.simulate_collusion(
            adv.CollusionScenario(
                base=_make_base_scenario(),
                num_colluders=10,
                coordinated_votes=[1.0] * 10,
                coordinated_weights=[100.0] * 10,
            )
        )
        assert "flipped" in result_success.notes.lower()

        result_fail = adv.simulate_collusion(
            adv.CollusionScenario(
                base=_make_base_scenario(), num_colluders=1
            )
        )
        assert (
            "achieved" in result_fail.notes.lower()
            or "variance" in result_fail.notes.lower()
        )


# ---------------------------------------------------------------------------
# Collusion equivalence check
# ---------------------------------------------------------------------------


class TestCollusionEquivalenceCheck:
    def test_returns_tuple(self) -> None:
        coll, single = adv.collusion_equivalence_check(
            _make_base_scenario(), num_colluders=5, total_weight=300.0
        )
        assert isinstance(coll, adv.CollusionResult)
        assert isinstance(single, sybil.AttackResult)

    def test_at_bound_both_flip(self) -> None:
        base = _make_base_scenario()
        single = sybil.min_weight_to_flip(base)
        coll, single_again = adv.collusion_equivalence_check(
            base,
            num_colluders=5,
            total_weight=single.min_total_sybil_weight,
        )
        assert coll.success is True
        assert single_again.is_feasible

    def test_below_bound_both_fail(self) -> None:
        base = _make_base_scenario()
        single = sybil.min_weight_to_flip(base)
        coll, _ = adv.collusion_equivalence_check(
            base,
            num_colluders=3,
            total_weight=single.min_total_sybil_weight * 0.5,
        )
        assert coll.success is False


# ---------------------------------------------------------------------------
# AdaptiveScenario validation
# ---------------------------------------------------------------------------


class TestAdaptiveScenarioValidation:
    def test_default_construction(self) -> None:
        s = adv.AdaptiveScenario(base=_make_base_scenario())
        assert s.num_sybils == 1
        assert s.max_weight_per_sybil == weights.BASE_WEIGHT

    def test_rejects_zero_sybils(self) -> None:
        with pytest.raises(ValueError, match="num_sybils"):
            adv.AdaptiveScenario(base=_make_base_scenario(), num_sybils=0)

    def test_rejects_negative_weight_cap(self) -> None:
        with pytest.raises(ValueError, match="max_weight_per_sybil"):
            adv.AdaptiveScenario(
                base=_make_base_scenario(), max_weight_per_sybil=-1.0
            )


# ---------------------------------------------------------------------------
# Adaptive attacker
# ---------------------------------------------------------------------------


class TestMinAdaptiveWeight:
    def test_zero_when_already_target(self) -> None:
        result = adv.min_adaptive_weight(
            adv.AdaptiveScenario(base=_make_yes_already_winning())
        )
        assert result.is_feasible is True
        assert result.min_total_weight == 0.0
        assert "no attack" in result.optimal_strategy.lower()

    def test_concentrated_strategy_matches_single_sybil_bound(self) -> None:
        """At num_sybils=1, adaptive analysis collapses to the
        single-attacker concentrated-vote bound."""
        base = _make_base_scenario()
        adaptive = adv.min_adaptive_weight(
            adv.AdaptiveScenario(
                base=base, num_sybils=1, max_weight_per_sybil=1e9
            )
        )
        single = sybil.min_weight_to_flip(base)
        assert adaptive.min_total_weight == pytest.approx(
            single.min_total_sybil_weight, rel=1e-3
        )

    def test_spread_strategy_with_multiple_sybils(self) -> None:
        """With multiple Sybils, the optimal strategy is at most as
        expensive as the concentrated one — spread can never be worse."""
        base = _make_base_scenario()
        single = sybil.min_weight_to_flip(base)
        adaptive = adv.min_adaptive_weight(
            adv.AdaptiveScenario(
                base=base, num_sybils=4, max_weight_per_sybil=1e9
            )
        )
        assert adaptive.min_total_weight <= single.min_total_sybil_weight + 1e-6

    def test_budget_infeasibility(self) -> None:
        """When the budget is too small to cover the optimal strategy,
        is_feasible is False but min_total_weight still reports the cost."""
        base = _make_base_scenario()
        # 1 Sybil, max weight 1.0 — far below the ~272 needed
        adaptive = adv.min_adaptive_weight(
            adv.AdaptiveScenario(
                base=base, num_sybils=1, max_weight_per_sybil=1.0
            )
        )
        assert adaptive.is_feasible is False
        assert adaptive.budget_total == pytest.approx(1.0)
        assert adaptive.min_total_weight > adaptive.budget_total

    def test_strategy_description_is_human_readable(self) -> None:
        base = _make_base_scenario()
        adaptive = adv.min_adaptive_weight(
            adv.AdaptiveScenario(
                base=base, num_sybils=2, max_weight_per_sybil=1e9
            )
        )
        # Should mention vote, weight, or strategy choice
        s = adaptive.optimal_strategy.lower()
        assert any(k in s for k in ("vote", "weight", "split", "concentrated"))


# ---------------------------------------------------------------------------
# BriberyScenario validation
# ---------------------------------------------------------------------------


class TestBriberyScenarioValidation:
    def test_defaults(self) -> None:
        scen = adv.BriberyScenario(base=_make_base_scenario())
        assert scen.cost_per_agent_usd == adv.DEFAULT_BRIBERY_COST_USD
        assert scen.flipped_vote is None

    def test_rejects_negative_cost(self) -> None:
        with pytest.raises(ValueError, match="cost_per_agent_usd"):
            adv.BriberyScenario(
                base=_make_base_scenario(), cost_per_agent_usd=-1.0
            )

    def test_rejects_out_of_range_vote(self) -> None:
        with pytest.raises(ValueError, match="flipped_vote"):
            adv.BriberyScenario(
                base=_make_base_scenario(), flipped_vote=1.5
            )


# ---------------------------------------------------------------------------
# Bribery
# ---------------------------------------------------------------------------


class TestMinBriberyCost:
    def test_zero_cost_when_already_target(self) -> None:
        result = adv.min_bribery_cost(
            adv.BriberyScenario(base=_make_yes_already_winning())
        )
        assert result.is_feasible is True
        assert result.num_agents_flipped == 0
        assert result.min_cost_usd == 0.0
        assert result.flipped_agent_ids == []

    def test_greedy_flips_highest_weight_first(self) -> None:
        """With weights 3, 2, 1 the algorithm picks the weight-3 agent
        first, then weight-2, then weight-1."""
        votes = [
            consensus.AgentVote(agent_id="low", probability=0.1, confidence=0.9),
            consensus.AgentVote(agent_id="mid", probability=0.1, confidence=0.9),
            consensus.AgentVote(agent_id="high", probability=0.1, confidence=0.9),
        ]
        scen = sybil.AttackScenario(
            honest_votes=votes,
            honest_weights={"low": 1.0, "mid": 2.0, "high": 3.0},
            target_decision="YES",
        )
        result = adv.min_bribery_cost(
            adv.BriberyScenario(base=scen, cost_per_agent_usd=100.0)
        )
        assert result.is_feasible is True
        # First flipped should be 'high' (highest weight)
        assert result.flipped_agent_ids[0] == "high"

    def test_cost_is_count_times_unit_price(self) -> None:
        votes = [
            consensus.AgentVote(agent_id=f"a{i}", probability=0.1, confidence=0.9)
            for i in range(5)
        ]
        scen = sybil.AttackScenario(
            honest_votes=votes,
            honest_weights={f"a{i}": 1.0 for i in range(5)},
            target_decision="YES",
        )
        result = adv.min_bribery_cost(
            adv.BriberyScenario(base=scen, cost_per_agent_usd=500.0)
        )
        if result.is_feasible:
            assert result.min_cost_usd == pytest.approx(
                result.num_agents_flipped * 500.0
            )

    def test_deterministic_tiebreak(self) -> None:
        """Equal-weight ties broken by agent_id alphabetically."""
        votes = [
            consensus.AgentVote(agent_id="zebra", probability=0.1, confidence=0.9),
            consensus.AgentVote(agent_id="alpha", probability=0.1, confidence=0.9),
        ]
        scen = sybil.AttackScenario(
            honest_votes=votes,
            honest_weights={"zebra": 5.0, "alpha": 5.0},
            target_decision="YES",
        )
        result = adv.min_bribery_cost(adv.BriberyScenario(base=scen))
        assert result.flipped_agent_ids[0] == "alpha"

    def test_default_flipped_vote_matches_target(self) -> None:
        """YES target → flipped_vote=1.0; NO target → flipped_vote=0.0."""
        scen_yes = sybil.AttackScenario(
            honest_votes=[
                consensus.AgentVote(agent_id="a", probability=0.5, confidence=0.9)
            ],
            honest_weights={"a": 1.0},
            target_decision="YES",
        )
        result_yes = adv.min_bribery_cost(adv.BriberyScenario(base=scen_yes))
        # Confirm via notes that flipped_vote=1.00 was used
        assert "1.00" in result_yes.notes

        scen_no = sybil.AttackScenario(
            honest_votes=[
                consensus.AgentVote(agent_id="a", probability=0.5, confidence=0.9)
            ],
            honest_weights={"a": 1.0},
            target_decision="NO",
        )
        result_no = adv.min_bribery_cost(adv.BriberyScenario(base=scen_no))
        assert "0.00" in result_no.notes

    def test_explicit_flipped_vote_used(self) -> None:
        scen = sybil.AttackScenario(
            honest_votes=[
                consensus.AgentVote(agent_id="a", probability=0.5, confidence=0.9)
            ],
            honest_weights={"a": 1.0},
            target_decision="YES",
        )
        result = adv.min_bribery_cost(
            adv.BriberyScenario(base=scen, flipped_vote=0.9)
        )
        assert "0.90" in result.notes

    def test_infeasibility_when_target_unreachable(self) -> None:
        """If flipped_vote is on the wrong side of the threshold, even
        flipping every agent won't move the decision."""
        votes = [
            consensus.AgentVote(agent_id="a", probability=0.5, confidence=0.9)
        ]
        scen = sybil.AttackScenario(
            honest_votes=votes,
            honest_weights={"a": 1.0},
            target_decision="YES",
        )
        result = adv.min_bribery_cost(
            adv.BriberyScenario(
                base=scen, flipped_vote=0.50  # below yes_threshold 0.85
            )
        )
        assert result.is_feasible is False
        assert result.min_cost_usd == math.inf

    def test_demo_scenario_bribery(self) -> None:
        """Sanity-check the demo scenario: bribery should be feasible
        (since with 3 honest agents you can always flip 2 or 3)."""
        result = adv.min_bribery_cost(adv.demo_bribery_scenario())
        # Always feasible for 3-agent demo: flipping all 3 gets you to
        # probability ≈ 1.0 (all voting 1.0) clearing the YES threshold
        assert result.is_feasible is True
        assert 1 <= result.num_agents_flipped <= 3


# ---------------------------------------------------------------------------
# Composed attacks
# ---------------------------------------------------------------------------


class TestComposeAttacks:
    def test_returns_both_costs(self) -> None:
        result = adv.compose_attacks(_make_base_scenario())
        assert isinstance(result.sybil_cost_usd, float)
        assert isinstance(result.bribery_cost_usd, float)
        assert result.cheapest_vector in ("sybil", "bribery", "infeasible")

    def test_bribery_cheaper_for_small_swarm(self) -> None:
        """3 honest agents: bribery at $250 × 2 = $500 typically beats
        registering ~272 Sybils at $5 each = $1,360."""
        result = adv.compose_attacks(
            _make_base_scenario(),
            registry_cost_usd=5.0,
            bribery_cost_usd=250.0,
        )
        # Both should be feasible and finite
        assert result.sybil_cost_usd != math.inf
        assert result.bribery_cost_usd != math.inf
        # For the canonical demo, bribery is cheaper
        assert result.cheapest_vector == "bribery"
        assert result.cheapest_cost_usd == result.bribery_cost_usd

    def test_sybil_cheaper_when_bribery_expensive(self) -> None:
        """At very high bribery cost per agent, Sybil dominates."""
        result = adv.compose_attacks(
            _make_base_scenario(),
            registry_cost_usd=1.0,
            bribery_cost_usd=1_000_000.0,
        )
        assert result.cheapest_vector == "sybil"

    def test_cheapest_cost_is_minimum(self) -> None:
        result = adv.compose_attacks(_make_base_scenario())
        candidates = []
        if result.sybil_cost_usd != math.inf:
            candidates.append(result.sybil_cost_usd)
        if result.bribery_cost_usd != math.inf:
            candidates.append(result.bribery_cost_usd)
        if candidates:
            assert result.cheapest_cost_usd == min(candidates)

    def test_notes_explain_choice(self) -> None:
        result = adv.compose_attacks(_make_base_scenario())
        assert len(result.notes) > 0
        # Either describes feasibility or compares costs
        assert any(
            tok in result.notes.lower()
            for tok in ("cheaper", "feasible", "infeasible", "only feasible")
        )


# ---------------------------------------------------------------------------
# Pretty-printers
# ---------------------------------------------------------------------------


class TestFormatters:
    def test_format_collusion_includes_key_fields(self) -> None:
        result = adv.simulate_collusion(
            adv.CollusionScenario(base=_make_base_scenario(), num_colluders=3)
        )
        text = adv.format_collusion_text(result)
        assert "Total Sybil weight" in text
        assert "Achieved decision" in text
        assert "Attack succeeded" in text

    def test_format_collusion_asymmetric_shows_na(self) -> None:
        result = adv.simulate_collusion(
            adv.CollusionScenario(
                base=_make_base_scenario(),
                num_colluders=2,
                coordinated_votes=[0.8, 0.6],
            )
        )
        text = adv.format_collusion_text(result)
        assert "n/a" in text.lower() or "nan" in text.lower()

    def test_format_adaptive_includes_strategy(self) -> None:
        result = adv.min_adaptive_weight(
            adv.AdaptiveScenario(base=_make_base_scenario())
        )
        text = adv.format_adaptive_text(result)
        assert "Optimal strategy" in text
        assert "Budget" in text

    def test_format_bribery_includes_cost_and_agents(self) -> None:
        result = adv.min_bribery_cost(
            adv.BriberyScenario(base=_make_base_scenario())
        )
        text = adv.format_bribery_text(result)
        assert "Agents to flip" in text
        assert "Total cost" in text
        assert "Flipped agent IDs" in text

    def test_format_bribery_infeasible(self) -> None:
        votes = [consensus.AgentVote(agent_id="a", probability=0.5, confidence=0.9)]
        scen = sybil.AttackScenario(
            honest_votes=votes,
            honest_weights={"a": 1.0},
            target_decision="YES",
        )
        result = adv.min_bribery_cost(
            adv.BriberyScenario(base=scen, flipped_vote=0.5)
        )
        text = adv.format_bribery_text(result)
        assert "infeasible" in text.lower() or "∞" in text

    def test_format_composed_includes_both_vectors(self) -> None:
        result = adv.compose_attacks(_make_base_scenario())
        text = adv.format_composed_text(result)
        assert "Sybil cost" in text
        assert "Bribery cost" in text
        assert "Cheapest" in text

    def test_format_composed_infeasible_section(self) -> None:
        # Force infeasibility by giving a scenario with no feasibility
        votes = [
            consensus.AgentVote(agent_id="a", probability=0.5, confidence=0.9)
        ]
        scen = sybil.AttackScenario(
            honest_votes=votes,
            honest_weights={"a": 1.0},
            target_decision="YES",
            attacker_vote=0.5,  # forces sybil infeasibility too
        )
        composed = adv.compose_attacks(scen)
        text = adv.format_composed_text(composed)
        assert "infeasible" in text.lower() or "∞" in text


# ---------------------------------------------------------------------------
# Demo scenarios
# ---------------------------------------------------------------------------


class TestDemoScenarios:
    def test_collusion_demo(self) -> None:
        s = adv.demo_collusion_scenario(num_colluders=5, target_decision="YES")
        assert s.num_colluders == 5
        assert s.base.target_decision == "YES"

    def test_collusion_demo_default(self) -> None:
        s = adv.demo_collusion_scenario()
        assert s.num_colluders == 3

    def test_adaptive_demo(self) -> None:
        s = adv.demo_adaptive_scenario(num_sybils=10)
        assert s.num_sybils == 10
        assert s.max_weight_per_sybil > 1.0  # generous budget

    def test_bribery_demo(self) -> None:
        s = adv.demo_bribery_scenario(cost_per_agent_usd=500.0)
        assert s.cost_per_agent_usd == 500.0

    def test_bribery_demo_no_target(self) -> None:
        s = adv.demo_bribery_scenario(target_decision="NO")
        assert s.base.target_decision == "NO"


# ---------------------------------------------------------------------------
# Cross-method invariants
# ---------------------------------------------------------------------------


class TestCrossMethodInvariants:
    def test_collusion_with_equivalent_weight_matches_single_sybil_decision(self) -> None:
        """For every num_colluders, a symmetric all-target-vote attack
        slightly above the single-Sybil bound flips the decision (1% above
        the bound — see ``test_symmetric_collusion_lemma`` for the
        floating-point rationale)."""
        base = _make_base_scenario("YES")
        single = sybil.min_weight_to_flip(base)
        total_w = single.min_total_sybil_weight * 1.01
        for k in [1, 3, 7, 50]:
            coll = adv.simulate_collusion(
                adv.CollusionScenario(
                    base=base,
                    num_colluders=k,
                    coordinated_votes=[1.0] * k,
                    coordinated_weights=[total_w / k] * k,
                )
            )
            assert coll.success is True

    def test_adaptive_no_worse_than_concentrated(self) -> None:
        """Adaptive (multi-Sybil) is never strictly worse than the
        concentrated single-Sybil bound."""
        for target in ("YES", "NO"):
            base = _make_base_scenario(target)  # type: ignore[arg-type]
            single = sybil.min_weight_to_flip(base)
            adaptive = adv.min_adaptive_weight(
                adv.AdaptiveScenario(
                    base=base, num_sybils=5, max_weight_per_sybil=1e9
                )
            )
            # Allow a tiny numerical slack
            assert (
                adaptive.min_total_weight <= single.min_total_sybil_weight + 1e-3
            ), f"target={target}: adaptive {adaptive.min_total_weight} > single {single.min_total_sybil_weight}"

    def test_bribery_cost_monotone_in_unit_price(self) -> None:
        """Doubling the per-agent bribery cost doubles the total
        bribery cost (for feasible attacks)."""
        base = _make_base_scenario()
        r1 = adv.min_bribery_cost(
            adv.BriberyScenario(base=base, cost_per_agent_usd=100.0)
        )
        r2 = adv.min_bribery_cost(
            adv.BriberyScenario(base=base, cost_per_agent_usd=200.0)
        )
        if r1.is_feasible and r2.is_feasible:
            assert r1.num_agents_flipped == r2.num_agents_flipped
            assert r2.min_cost_usd == pytest.approx(r1.min_cost_usd * 2.0)


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------


class TestPublicSurface:
    def test_all_exports_resolve(self) -> None:
        for name in adv.__all__:
            assert hasattr(adv, name), f"Missing export: {name}"

    def test_main_attack_functions_present(self) -> None:
        for fn in (
            "simulate_collusion",
            "min_adaptive_weight",
            "min_bribery_cost",
            "compose_attacks",
        ):
            assert callable(getattr(adv, fn))

    def test_default_bribery_cost_positive(self) -> None:
        assert adv.DEFAULT_BRIBERY_COST_USD > 0.0
