"""Tests for the Sybil-resistance analysis module.

Coverage:
- AttackScenario validation (input shape, threshold sanity, vote bounds)
- Baseline-decision invariance (cost is 0 when honest swarm already produces target)
- YES / NO flip closed-form math: matches numeric reproduction by direct
  consensus aggregation
- Infeasibility detection (attacker_vote on wrong side of threshold)
- DISPUTE-target dual paths (band crossing vs variance inflation)
- ``expected_brier_constant_voter`` math (minimum at base rate)
- ``max_calibration_weight_constant_voter`` matches direct call to
  ``compute_weight``
- ``sybil_break_even_predictions`` agrees with the inverse formula
- ``protocol_security_margin`` integration: end-to-end summary
- ``format_margin_text`` covers all branches
- ``demo_scenario`` produces the canonical README state
- Edge cases: zero-weight honest swarm, single-vote swarm, unanimous swarm,
  threshold boundary cases, attacker_vote = threshold (degenerate denominator)
"""
from __future__ import annotations

import math
from typing import Literal

import pytest

from swarm_oracle import consensus as _consensus
from swarm_oracle import sybil as _sybil
from swarm_oracle import weights as _weights


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def calibrated_scenario_yes_target() -> _sybil.AttackScenario:
    """Honest swarm leans NO; attacker wants YES."""
    return _sybil.demo_scenario("YES")


@pytest.fixture
def calibrated_scenario_no_target() -> _sybil.AttackScenario:
    """Same honest swarm; attacker wants NO (i.e. defending baseline)."""
    return _sybil.demo_scenario("NO")


@pytest.fixture
def calibrated_scenario_dispute_target() -> _sybil.AttackScenario:
    return _sybil.demo_scenario("DISPUTE")


def _vote(agent_id: str, p: float, conf: float = 0.7) -> _consensus.AgentVote:
    return _consensus.AgentVote(
        agent_id=agent_id, probability=p, confidence=conf
    )


# ---------------------------------------------------------------------------
# AttackScenario construction
# ---------------------------------------------------------------------------


class TestAttackScenarioValidation:
    def test_rejects_empty_votes(self):
        with pytest.raises(ValueError, match="at least one honest vote"):
            _sybil.AttackScenario(
                honest_votes=[],
                honest_weights={},
                target_decision="YES",
            )

    @pytest.mark.parametrize("bad", ["MAYBE", "yes", "no", "", "FLIP"])
    def test_rejects_invalid_target_decision(self, bad):
        with pytest.raises(ValueError, match="target_decision"):
            _sybil.AttackScenario(
                honest_votes=[_vote("a", 0.5)],
                honest_weights={"a": 1.0},
                target_decision=bad,  # type: ignore[arg-type]
            )

    @pytest.mark.parametrize("bad", [-0.01, 1.01, 2.0, -100.0])
    def test_rejects_attacker_vote_outside_unit_interval(self, bad):
        with pytest.raises(ValueError, match="attacker_vote"):
            _sybil.AttackScenario(
                honest_votes=[_vote("a", 0.5)],
                honest_weights={"a": 1.0},
                target_decision="YES",
                attacker_vote=bad,
            )

    def test_accepts_attacker_vote_none(self):
        s = _sybil.AttackScenario(
            honest_votes=[_vote("a", 0.5)],
            honest_weights={"a": 1.0},
            target_decision="YES",
            attacker_vote=None,
        )
        assert s.attacker_vote is None


# ---------------------------------------------------------------------------
# Baseline decision invariance
# ---------------------------------------------------------------------------


class TestBaselineInvariance:
    def test_zero_cost_when_honest_already_produces_target(self):
        # Honest agents already vote YES with high confidence.
        votes = [
            _vote("a", 0.95),
            _vote("b", 0.92),
            _vote("c", 0.96),
        ]
        weights = {"a": 5.0, "b": 5.0, "c": 5.0}
        scenario = _sybil.AttackScenario(
            honest_votes=votes,
            honest_weights=weights,
            target_decision="YES",
        )
        result = _sybil.min_weight_to_flip(scenario)
        assert result.is_feasible is True
        assert result.min_total_sybil_weight == 0.0
        assert result.min_base_weight_sybils == 0
        assert result.baseline_decision == "YES"
        assert "no attack needed" in result.notes.lower()

    def test_zero_cost_when_no_target_is_baseline(
        self, calibrated_scenario_no_target
    ):
        # Demo scenario produces a NO baseline; attacker wants NO too.
        result = _sybil.min_weight_to_flip(calibrated_scenario_no_target)
        assert result.is_feasible is True
        assert result.min_total_sybil_weight == 0.0


# ---------------------------------------------------------------------------
# YES-flip closed-form math
# ---------------------------------------------------------------------------


def _simulate_flip(
    scenario: _sybil.AttackScenario, total_sybil_weight: float
) -> _consensus.ConsensusResult:
    """Re-run the consensus engine with one synthetic Sybil contributor
    representing the entire injected mass.
    """
    p_s = (
        scenario.attacker_vote
        if scenario.attacker_vote is not None
        else {"YES": 1.0, "NO": 0.0, "DISPUTE": 0.5}[scenario.target_decision]
    )
    sybil_vote = _vote("sybil-mass", p_s)
    weights_with_sybil = dict(scenario.honest_weights)
    weights_with_sybil["sybil-mass"] = total_sybil_weight
    return _consensus.aggregate_consensus(
        scenario.honest_votes + [sybil_vote],
        weights_with_sybil,
        yes_threshold=scenario.yes_threshold,
        no_threshold=scenario.no_threshold,
        variance_threshold=scenario.variance_threshold,
        default_weight=scenario.default_weight,
    )


class TestYesFlipMath:
    def test_returns_feasible_for_yes_target(
        self, calibrated_scenario_yes_target
    ):
        result = _sybil.min_weight_to_flip(calibrated_scenario_yes_target)
        assert result.is_feasible is True
        assert result.min_total_sybil_weight > 0.0
        assert isinstance(result.min_base_weight_sybils, int)
        assert result.min_base_weight_sybils >= math.ceil(
            result.min_total_sybil_weight
        )

    def test_minimum_weight_produces_yes_decision(
        self, calibrated_scenario_yes_target
    ):
        result = _sybil.min_weight_to_flip(calibrated_scenario_yes_target)
        # At a tiny epsilon above the computed minimum, decision should be YES.
        cushion = result.min_total_sybil_weight + 1e-6
        sim = _simulate_flip(calibrated_scenario_yes_target, cushion)
        assert sim.decision == "YES"

    def test_weight_just_below_minimum_does_not_flip(
        self, calibrated_scenario_yes_target
    ):
        result = _sybil.min_weight_to_flip(calibrated_scenario_yes_target)
        if result.min_total_sybil_weight <= 1e-3:
            pytest.skip("cost too small to safely subtract epsilon")
        below = result.min_total_sybil_weight - 1e-3
        sim = _simulate_flip(calibrated_scenario_yes_target, below)
        # Decision is either NO or DISPUTE — anything *but* YES.
        assert sim.decision != "YES"

    def test_attacker_vote_at_or_below_threshold_infeasible(self):
        # Attacker promises p=0.85 which is exactly the YES threshold; no
        # positive Sybil weight pushes consensus *strictly* above.
        votes = [_vote("a", 0.10), _vote("b", 0.20)]
        weights = {"a": 5.0, "b": 5.0}
        scenario = _sybil.AttackScenario(
            honest_votes=votes,
            honest_weights=weights,
            target_decision="YES",
            attacker_vote=0.85,
        )
        result = _sybil.min_weight_to_flip(scenario)
        assert result.is_feasible is False
        assert result.min_total_sybil_weight == math.inf
        assert result.min_base_weight_sybils == math.inf
        assert "yes_threshold" in result.notes.lower() or "threshold" in result.notes.lower()


# ---------------------------------------------------------------------------
# NO-flip closed-form math
# ---------------------------------------------------------------------------


class TestNoFlipMath:
    def test_flip_yes_baseline_to_no(self):
        # Honest swarm decisive YES; attacker wants NO.
        votes = [_vote("a", 0.95), _vote("b", 0.92), _vote("c", 0.96)]
        weights = {"a": 5.0, "b": 5.0, "c": 5.0}
        scenario = _sybil.AttackScenario(
            honest_votes=votes,
            honest_weights=weights,
            target_decision="NO",
        )
        result = _sybil.min_weight_to_flip(scenario)
        assert result.is_feasible is True
        # Simulation should produce NO at the boundary.
        sim = _simulate_flip(scenario, result.min_total_sybil_weight + 1e-6)
        assert sim.decision == "NO"

    def test_attacker_vote_at_or_above_no_threshold_infeasible(self):
        # NO threshold is 0.15; attacker votes 0.5 — cannot push below.
        votes = [_vote("a", 0.95), _vote("b", 0.92)]
        weights = {"a": 5.0, "b": 5.0}
        scenario = _sybil.AttackScenario(
            honest_votes=votes,
            honest_weights=weights,
            target_decision="NO",
            attacker_vote=0.5,
        )
        result = _sybil.min_weight_to_flip(scenario)
        assert result.is_feasible is False
        assert result.min_total_sybil_weight == math.inf


# ---------------------------------------------------------------------------
# Dispute target
# ---------------------------------------------------------------------------


class TestDisputeFlipMath:
    def test_dispute_flip_from_decisive_yes(self):
        # Honest swarm decisive YES; attacker wants DISPUTE.
        votes = [_vote("a", 0.95), _vote("b", 0.92), _vote("c", 0.96)]
        weights = {"a": 5.0, "b": 5.0, "c": 5.0}
        scenario = _sybil.AttackScenario(
            honest_votes=votes,
            honest_weights=weights,
            target_decision="DISPUTE",
            attacker_vote=0.0,
        )
        result = _sybil.min_weight_to_flip(scenario)
        assert result.is_feasible is True
        # Simulating at the cost should produce DISPUTE.
        sim = _simulate_flip(scenario, result.min_total_sybil_weight + 1e-3)
        assert sim.decision == "DISPUTE"

    def test_dispute_flip_from_decisive_no(self):
        # Decisive NO baseline; attacker injects 1.0 votes to push into band.
        votes = [_vote("a", 0.05), _vote("b", 0.07)]
        weights = {"a": 3.0, "b": 3.0}
        scenario = _sybil.AttackScenario(
            honest_votes=votes,
            honest_weights=weights,
            target_decision="DISPUTE",
            attacker_vote=1.0,
        )
        result = _sybil.min_weight_to_flip(scenario)
        assert result.is_feasible is True
        sim = _simulate_flip(scenario, result.min_total_sybil_weight + 1e-3)
        assert sim.decision == "DISPUTE"

    def test_dispute_at_baseline_zero_cost(self):
        # Honest swarm already disputes — variance high.
        votes = [_vote("a", 0.10), _vote("b", 0.90)]
        weights = {"a": 1.0, "b": 1.0}
        scenario = _sybil.AttackScenario(
            honest_votes=votes,
            honest_weights=weights,
            target_decision="DISPUTE",
        )
        baseline = _sybil.baseline_consensus(scenario)
        assert baseline.decision == "DISPUTE"
        result = _sybil.min_weight_to_flip(scenario)
        assert result.is_feasible is True
        assert result.min_total_sybil_weight == 0.0

    def test_notes_describe_winning_path(self):
        # When the band crossing is much cheaper, the notes should say so.
        votes = [_vote("a", 0.95), _vote("b", 0.92), _vote("c", 0.96)]
        weights = {"a": 5.0, "b": 5.0, "c": 5.0}
        scenario = _sybil.AttackScenario(
            honest_votes=votes,
            honest_weights=weights,
            target_decision="DISPUTE",
            attacker_vote=0.0,
        )
        result = _sybil.min_weight_to_flip(scenario)
        assert "dispute path" in result.notes.lower()


# ---------------------------------------------------------------------------
# Zero-weight honest swarm
# ---------------------------------------------------------------------------


class TestZeroWeightHonestSwarm:
    def test_yes_target_infeasible_when_honest_weights_zero(self):
        votes = [_vote("a", 0.10), _vote("b", 0.20)]
        weights = {"a": 0.0, "b": 0.0}
        scenario = _sybil.AttackScenario(
            honest_votes=votes,
            honest_weights=weights,
            target_decision="YES",
            default_weight=0.0,
        )
        result = _sybil.min_weight_to_flip(scenario)
        # Falls back to unweighted mean; consensus = 0.15 < 0.85 yes-threshold.
        # Reported as infeasible by the closed-form solver because honest
        # weight is zero (the protocol degrades gracefully but the solver
        # flags this corner case).
        assert result.is_feasible is False
        assert "weights sum to zero" in result.notes.lower()


# ---------------------------------------------------------------------------
# Constant-voter Brier / calibration ceiling
# ---------------------------------------------------------------------------


class TestExpectedBrierConstantVoter:
    @pytest.mark.parametrize(
        "vote,rate,expected",
        [
            (1.0, 0.5, 0.5),
            (0.0, 0.5, 0.5),
            (0.5, 0.5, 0.25),  # minimum at p = base rate
            (1.0, 0.8, 0.2),
            (0.0, 0.2, 0.2),
            (0.5, 0.2, 0.25),  # constant 0.5 against rate 0.2
        ],
    )
    def test_known_values(self, vote, rate, expected):
        got = _sybil.expected_brier_constant_voter(vote, rate)
        assert math.isclose(got, expected, abs_tol=1e-9)

    def test_minimum_achieved_at_base_rate(self):
        # For each base rate r, p = r minimizes the expected Brier.
        for r in (0.1, 0.3, 0.5, 0.7, 0.9):
            at_r = _sybil.expected_brier_constant_voter(r, r)
            for p in (0.0, 0.2, 0.4, 0.6, 0.8, 1.0):
                assert _sybil.expected_brier_constant_voter(p, r) >= at_r - 1e-9

    def test_min_expected_brier_equals_bernoulli_variance(self):
        for r in (0.1, 0.25, 0.5, 0.75, 0.9):
            assert math.isclose(
                _sybil.min_expected_brier_constant_voter(r),
                r * (1 - r),
                abs_tol=1e-9,
            )

    @pytest.mark.parametrize("bad", [-0.01, 1.01, math.nan])
    def test_rejects_invalid_inputs(self, bad):
        if math.isnan(bad):
            # NaN bypasses the range check via comparison; protocol math
            # treats NaN as invalid range too.
            with pytest.raises(ValueError):
                _sybil.expected_brier_constant_voter(bad, 0.5)
        else:
            with pytest.raises(ValueError):
                _sybil.expected_brier_constant_voter(bad, 0.5)
            with pytest.raises(ValueError):
                _sybil.expected_brier_constant_voter(0.5, bad)


class TestMaxCalibrationWeightConstantVoter:
    def test_matches_compute_weight_direct(self):
        for r in (0.1, 0.3, 0.5, 0.7, 0.9):
            ceiling = _sybil.max_calibration_weight_constant_voter(r)
            direct = _weights.compute_weight(
                r * (1 - r), _weights.CONFIDENCE_THRESHOLD
            )
            assert math.isclose(ceiling, direct, abs_tol=1e-9)

    def test_ceiling_below_oracle_weight(self):
        # An oracle-tier agent (Brier 0.10, 100+ predictions) has weight ~9.99.
        # A constant-voter Sybil cannot reach that ceiling for any base rate
        # in (0, 1) except in the trivial r→0 / r→1 limits which require
        # the Sybil to vote 0 or 1 against a near-deterministic outcome —
        # i.e. the Sybil is "right" because the outcome is trivial, which
        # the protocol naturally rewards.
        oracle_weight = _weights.compute_weight(
            0.10, _weights.CONFIDENCE_THRESHOLD
        )
        ceiling_at_balanced = _sybil.max_calibration_weight_constant_voter(0.5)
        assert ceiling_at_balanced < oracle_weight


# ---------------------------------------------------------------------------
# Break-even predictions
# ---------------------------------------------------------------------------


class TestBreakEvenPredictions:
    def test_zero_target_zero_predictions(self):
        assert _sybil.sybil_break_even_predictions(0.0, 0.25) == 0.0

    def test_inverse_relationship(self):
        # n = target * (brier + EPSILON) * CONFIDENCE_THRESHOLD
        target = 5.0
        brier = 0.18
        n = _sybil.sybil_break_even_predictions(target, brier)
        expected = max(
            float(_weights.MIN_PREDICTIONS),
            target * (brier + _weights.EPSILON) * _weights.CONFIDENCE_THRESHOLD,
        )
        assert math.isclose(n, expected, abs_tol=1e-9)

    def test_target_above_raw_max_returns_infinity(self):
        # Raw max at brier=0.25 is ~1/(0.25+0.001) = 3.984.
        # Target 5.0 is unattainable.
        n = _sybil.sybil_break_even_predictions(5.0, 0.25)
        assert n == math.inf

    def test_floor_at_min_predictions(self):
        # Very small target → floor returns MIN_PREDICTIONS.
        n = _sybil.sybil_break_even_predictions(0.01, 0.5)
        assert n == float(_weights.MIN_PREDICTIONS)

    @pytest.mark.parametrize("bad", [-0.01, 1.01, 2.0])
    def test_rejects_bad_brier(self, bad):
        with pytest.raises(ValueError):
            _sybil.sybil_break_even_predictions(1.0, bad)

    def test_negative_target_returns_zero(self):
        assert _sybil.sybil_break_even_predictions(-1.0, 0.25) == 0.0


# ---------------------------------------------------------------------------
# Protocol security margin (integration)
# ---------------------------------------------------------------------------


class TestProtocolSecurityMargin:
    def test_yes_target_demo(self, calibrated_scenario_yes_target):
        margin = _sybil.protocol_security_margin(calibrated_scenario_yes_target)
        assert margin.target_decision == "YES"
        assert margin.baseline_decision == "NO"
        assert margin.is_feasible_by_count is True
        assert margin.min_base_weight_sybils > 0
        # max attainable Sybil weight at base_rate=0.5 should be ~1/(0.25+EPS) ≈ 3.98
        assert math.isclose(
            margin.max_attainable_sybil_weight,
            _weights.compute_weight(0.25, _weights.CONFIDENCE_THRESHOLD),
            abs_tol=1e-6,
        )

    def test_predictions_to_match_oracle_uses_balanced_brier(
        self, calibrated_scenario_yes_target
    ):
        # At base_rate=0.5 the constant-voter's Brier is 0.25. The break-even
        # predictions for oracle weight should therefore equal
        # sybil_break_even_predictions(oracle_weight, 0.25).
        margin = _sybil.protocol_security_margin(
            calibrated_scenario_yes_target,
            base_rate=0.5,
            oracle_brier=0.10,
        )
        oracle_weight = _weights.compute_weight(
            0.10, _weights.CONFIDENCE_THRESHOLD
        )
        expected = _sybil.sybil_break_even_predictions(oracle_weight, 0.25)
        assert math.isclose(
            margin.predictions_to_match_oracle, expected, abs_tol=1e-9
        )


# ---------------------------------------------------------------------------
# Pretty-printing
# ---------------------------------------------------------------------------


class TestFormatMarginText:
    def test_feasible_output(self, calibrated_scenario_yes_target):
        margin = _sybil.protocol_security_margin(calibrated_scenario_yes_target)
        out = _sybil.format_margin_text(margin)
        assert "Baseline:" in out
        assert "Target:" in out
        assert "Cheap-Sybil cost:" in out
        assert "base-weight Sybils" in out
        assert "Sybil weight" in out

    def test_infeasible_output(self):
        votes = [_vote("a", 0.10), _vote("b", 0.20)]
        weights = {"a": 5.0, "b": 5.0}
        scenario = _sybil.AttackScenario(
            honest_votes=votes,
            honest_weights=weights,
            target_decision="YES",
            attacker_vote=0.5,  # below threshold → infeasible
        )
        margin = _sybil.protocol_security_margin(scenario)
        out = _sybil.format_margin_text(margin)
        assert "infeasible" in out.lower()

    def test_notes_included_when_present(self, calibrated_scenario_yes_target):
        # Manually craft a margin with a note.
        margin = _sybil.SecurityMargin(
            baseline_decision="NO",
            baseline_probability=0.15,
            target_decision="YES",
            min_base_weight_sybils=42,
            min_total_sybil_weight=41.1,
            is_feasible_by_count=True,
            base_rate_assumed=0.5,
            max_attainable_sybil_weight=3.98,
            predictions_to_match_oracle=2510.0,
            notes="Example annotation.",
        )
        out = _sybil.format_margin_text(margin)
        assert "Example annotation." in out


# ---------------------------------------------------------------------------
# Demo scenario
# ---------------------------------------------------------------------------


class TestDemoScenario:
    def test_three_agents_matching_weights_module(self):
        s = _sybil.demo_scenario("YES")
        ids = [v.agent_id for v in s.honest_votes]
        assert set(ids) == {"agent-oracle", "agent-reliable", "agent-novice"}
        # Weights come from mock history.
        expected = _weights.weights_from_history(_weights.mock_brier_history())
        assert s.honest_weights == expected

    def test_baseline_decision_is_no_in_demo(self):
        s = _sybil.demo_scenario("YES")
        baseline = _sybil.baseline_consensus(s)
        assert baseline.decision == "NO"

    @pytest.mark.parametrize("target", ["YES", "NO", "DISPUTE"])
    def test_demo_scenarios_run_without_errors(self, target):
        s = _sybil.demo_scenario(target)  # type: ignore[arg-type]
        result = _sybil.min_weight_to_flip(s)
        # Either feasible or we have notes explaining why not.
        assert result.is_feasible or result.notes


# ---------------------------------------------------------------------------
# Cross-method consistency
# ---------------------------------------------------------------------------


class TestCrossMethodConsistency:
    def test_min_sybils_to_flip_alias_returns_same_result(
        self, calibrated_scenario_yes_target
    ):
        a = _sybil.min_weight_to_flip(calibrated_scenario_yes_target)
        b = _sybil.min_sybils_to_flip(calibrated_scenario_yes_target)
        assert a == b

    def test_min_base_weight_sybils_ceils_weight(
        self, calibrated_scenario_yes_target
    ):
        result = _sybil.min_weight_to_flip(calibrated_scenario_yes_target)
        if result.is_feasible and result.min_total_sybil_weight != 0:
            assert (
                int(result.min_base_weight_sybils)
                == math.ceil(result.min_total_sybil_weight)
            )

    def test_yes_then_no_flips_form_a_consistent_story(self):
        # An honest swarm at p=0.50, with thresholds 0.85 / 0.15:
        # cost-to-YES and cost-to-NO should be symmetric. The closed-form
        # lower bound is (0.85 * 10 - 5) / 0.15 = 23.333, but the variance
        # gate raises the actual cost. By the protocol's left-right symmetry
        # at p=0.5, the two costs must still be equal to each other.
        votes = [_vote("a", 0.50), _vote("b", 0.50)]
        weights = {"a": 5.0, "b": 5.0}
        s_yes = _sybil.AttackScenario(
            honest_votes=votes, honest_weights=weights, target_decision="YES"
        )
        s_no = _sybil.AttackScenario(
            honest_votes=votes, honest_weights=weights, target_decision="NO"
        )
        r_yes = _sybil.min_weight_to_flip(s_yes)
        r_no = _sybil.min_weight_to_flip(s_no)
        assert r_yes.is_feasible and r_no.is_feasible
        # Symmetry: both directions cost the same.
        assert math.isclose(
            r_yes.min_total_sybil_weight,
            r_no.min_total_sybil_weight,
            rel_tol=1e-3,
        )
        # Cost must be at least the closed-form mean-crossing lower bound.
        closed_form_lb = (0.85 * 10 - 5) / 0.15
        assert r_yes.min_total_sybil_weight >= closed_form_lb - 1e-9


# ---------------------------------------------------------------------------
# Smoke: numeric formula reproduction for YES-flip
# ---------------------------------------------------------------------------


class TestYesFlipClosedForm:
    """The closed-form mean-crossing weight is a *lower bound* on the actual
    cost; the variance gate may make the true cost higher. These tests pin
    down both the lower bound and the simulation-confirmed upper bound.
    """

    @pytest.mark.parametrize(
        "p_honest_list,weight_list,expected_W,expected_A",
        [
            ([0.10, 0.20], [5.0, 5.0], 10.0, 1.5),
            ([0.50, 0.50, 0.50], [1.0, 1.0, 1.0], 3.0, 1.5),
            ([0.10, 0.18, 0.30], [10.0, 5.0, 1.0], 16.0, 1.0 + 0.9 + 0.3),
        ],
    )
    def test_closed_form_is_lower_bound(
        self, p_honest_list, weight_list, expected_W, expected_A
    ):
        votes = [_vote(f"a{i}", p) for i, p in enumerate(p_honest_list)]
        weights = {f"a{i}": w for i, w in enumerate(weight_list)}
        scenario = _sybil.AttackScenario(
            honest_votes=votes,
            honest_weights=weights,
            target_decision="YES",
        )
        result = _sybil.min_weight_to_flip(scenario)
        target = scenario.yes_threshold
        closed_form = (target * expected_W - expected_A) / (1 - target)
        if closed_form > 0:
            # Cost is AT LEAST the closed-form lower bound.
            assert (
                result.min_total_sybil_weight
                >= closed_form - 1e-6
            ), f"cost {result.min_total_sybil_weight} below LB {closed_form}"
        else:
            assert result.min_total_sybil_weight == 0.0

    @pytest.mark.parametrize(
        "p_honest_list,weight_list",
        [
            ([0.10, 0.20], [5.0, 5.0]),
            ([0.50, 0.50, 0.50], [1.0, 1.0, 1.0]),
            ([0.10, 0.18, 0.30], [10.0, 5.0, 1.0]),
        ],
    )
    def test_at_minimum_decision_is_target(self, p_honest_list, weight_list):
        votes = [_vote(f"a{i}", p) for i, p in enumerate(p_honest_list)]
        weights = {f"a{i}": w for i, w in enumerate(weight_list)}
        scenario = _sybil.AttackScenario(
            honest_votes=votes,
            honest_weights=weights,
            target_decision="YES",
        )
        result = _sybil.min_weight_to_flip(scenario)
        # Just above the computed minimum, simulation must produce target.
        cushion = result.min_total_sybil_weight * 1.001 + 1e-3
        sim = _simulate_flip(scenario, cushion)
        assert sim.decision == "YES"

    @pytest.mark.parametrize(
        "p_honest_list,weight_list",
        [
            ([0.10, 0.20], [5.0, 5.0]),
            ([0.10, 0.18, 0.30], [10.0, 5.0, 1.0]),
        ],
    )
    def test_just_below_minimum_does_not_flip(self, p_honest_list, weight_list):
        votes = [_vote(f"a{i}", p) for i, p in enumerate(p_honest_list)]
        weights = {f"a{i}": w for i, w in enumerate(weight_list)}
        scenario = _sybil.AttackScenario(
            honest_votes=votes,
            honest_weights=weights,
            target_decision="YES",
        )
        result = _sybil.min_weight_to_flip(scenario)
        if result.min_total_sybil_weight <= 1e-2:
            pytest.skip("cost too small to subtract a meaningful epsilon")
        below = result.min_total_sybil_weight * 0.999 - 1e-3
        if below <= 0:
            pytest.skip("subtracting epsilon goes non-positive")
        sim = _simulate_flip(scenario, below)
        # Decision should not yet be YES.
        assert sim.decision != "YES"


# ---------------------------------------------------------------------------
# AttackResult data-class invariants
# ---------------------------------------------------------------------------


class TestAttackResultInvariants:
    def test_immutable(self):
        with pytest.raises((AttributeError, Exception)):
            r = _sybil.AttackResult(
                is_feasible=True,
                min_total_sybil_weight=10.0,
                min_base_weight_sybils=10,
                baseline_decision="NO",
                baseline_probability=0.16,
                attacker_vote_used=1.0,
            )
            r.is_feasible = False  # type: ignore[misc]

    def test_infeasible_result_has_inf_count(self):
        votes = [_vote("a", 0.10), _vote("b", 0.20)]
        weights = {"a": 5.0, "b": 5.0}
        scenario = _sybil.AttackScenario(
            honest_votes=votes,
            honest_weights=weights,
            target_decision="YES",
            attacker_vote=0.5,
        )
        result = _sybil.min_weight_to_flip(scenario)
        assert result.is_feasible is False
        assert result.min_base_weight_sybils == math.inf


# ---------------------------------------------------------------------------
# Robustness: unanimous swarms and single-vote swarms
# ---------------------------------------------------------------------------


class TestEdgeSwarmShapes:
    def test_single_vote_swarm_yes_flip(self):
        votes = [_vote("a", 0.10)]
        weights = {"a": 10.0}
        scenario = _sybil.AttackScenario(
            honest_votes=votes,
            honest_weights=weights,
            target_decision="YES",
        )
        result = _sybil.min_weight_to_flip(scenario)
        assert result.is_feasible
        sim = _simulate_flip(scenario, result.min_total_sybil_weight + 1e-6)
        assert sim.decision == "YES"

    def test_unanimous_swarm_no_flip(self):
        # Everyone votes 0.05 — unanimously NO.
        votes = [_vote(f"a{i}", 0.05) for i in range(5)]
        weights = {f"a{i}": 5.0 for i in range(5)}
        scenario = _sybil.AttackScenario(
            honest_votes=votes,
            honest_weights=weights,
            target_decision="NO",
        )
        result = _sybil.min_weight_to_flip(scenario)
        assert result.is_feasible
        assert result.min_total_sybil_weight == 0.0


# ---------------------------------------------------------------------------
# Type annotations / public surface guard
# ---------------------------------------------------------------------------


class TestPublicSurface:
    @pytest.mark.parametrize(
        "name",
        [
            "AttackScenario",
            "AttackResult",
            "SecurityMargin",
            "baseline_consensus",
            "min_weight_to_flip",
            "min_sybils_to_flip",
            "expected_brier_constant_voter",
            "min_expected_brier_constant_voter",
            "max_calibration_weight_constant_voter",
            "sybil_break_even_predictions",
            "protocol_security_margin",
            "format_margin_text",
            "demo_scenario",
        ],
    )
    def test_symbol_exported(self, name):
        assert hasattr(_sybil, name), f"Expected sybil.{name} to be defined"
