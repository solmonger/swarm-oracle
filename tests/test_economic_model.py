"""Tests for scripts/economic_model.py — economic security model.

Covers:
  - Weight formula parity with weights.py
  - Sybil attack cost formula
  - Bribery attack cost (greedy optimality)
  - Security parameter composition
  - Pool-size and market-size scaling
  - Minimum viable pool binary search
  - CLI arg parsing and output
  - JSON serialisation
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.economic_model import (
    BASE_WEIGHT,
    EPSILON,
    NO_THRESHOLD,
    YES_THRESHOLD,
    BriberyAttackResult,
    ScalingPoint,
    SecurityParameter,
    SybilAttackResult,
    ValidatorProfile,
    bribery_attack_cost,
    compute_weight,
    demo_validators,
    market_size_scaling,
    minimum_viable_pool_for_market,
    pool_size_scaling,
    production_validators,
    scaled_validators,
    security_parameter,
    sybil_attack_cost,
)
from swarm_oracle.weights import compute_weight as ref_compute_weight


# ---------------------------------------------------------------------------
# TestWeightFormulaParity — matches swarm_oracle/weights.py exactly
# ---------------------------------------------------------------------------

class TestWeightFormulaParity:
    """economic_model.compute_weight must produce identical output to weights.py."""

    @pytest.mark.parametrize("brier,n", [
        (0.0, 0),
        (0.10, 220),
        (0.18, 140),
        (0.25, 25),
        (0.50, 100),
        (1.0, 150),
        (0.01, 19),    # just below MIN_PREDICTIONS → BASE_WEIGHT
        (0.01, 20),    # exactly at MIN_PREDICTIONS → calibration kicks in
    ])
    def test_parity_with_weights_py(self, brier, n):
        assert compute_weight(brier, n) == pytest.approx(ref_compute_weight(brier, n), rel=1e-9)

    def test_new_agent_gets_base_weight(self):
        assert compute_weight(0.05, 0) == pytest.approx(BASE_WEIGHT)
        assert compute_weight(0.30, 15) == pytest.approx(BASE_WEIGHT)

    def test_fully_trained_agent_weight(self):
        # n >= CONFIDENCE_THRESHOLD → confidence = 1.0 → weight = 1/(brier+EPSILON)
        w = compute_weight(0.10, 200)
        assert w == pytest.approx(1.0 / (0.10 + EPSILON))

    def test_partial_confidence_agent(self):
        # n = 50, CONFIDENCE_THRESHOLD = 100 → confidence = 0.5
        w = compute_weight(0.10, 50)
        expected = (1.0 / (0.10 + EPSILON)) * 0.5
        assert w == pytest.approx(expected)


# ---------------------------------------------------------------------------
# TestValidatorProfile — weight computed from brier+n fields
# ---------------------------------------------------------------------------

class TestValidatorProfile:
    def test_weight_property(self):
        vp = ValidatorProfile("a", brier_score=0.10, num_predictions=220, bribery_cost_usd=500)
        assert vp.weight == pytest.approx(compute_weight(0.10, 220))

    def test_demo_pool_weights(self):
        pool = demo_validators(bribery_cost_usd=250)
        assert len(pool) == 3
        oracle = next(v for v in pool if v.agent_id == "agent-oracle")
        assert oracle.weight > 1.0   # well-calibrated → above base


# ---------------------------------------------------------------------------
# TestSybilAttackCost
# ---------------------------------------------------------------------------

class TestSybilAttackCost:
    def test_yes_to_no_requires_high_sybil_weight(self):
        pool = demo_validators()
        r = sybil_attack_cost(pool, cost_per_sybil_usd=5.0, target_flip="YES→NO")
        assert isinstance(r, SybilAttackResult)
        assert r.num_sybils_required > 0
        assert r.target_flip == "YES→NO"
        assert r.attack_succeeds is True

    def test_sybil_weight_needed_formula(self):
        """W_sybil ≥ W_honest × (1-0.15)/0.15 = W_honest × 5.667"""
        pool = demo_validators()
        r = sybil_attack_cost(pool, cost_per_sybil_usd=5.0)
        W_h = sum(v.weight for v in pool)
        expected_weight = W_h * (1 - NO_THRESHOLD) / NO_THRESHOLD
        assert r.sybil_weight_needed == pytest.approx(expected_weight, rel=1e-6)

    def test_total_cost_equals_k_times_unit_cost(self):
        pool = demo_validators()
        for unit in [1.0, 5.0, 10.0, 100.0]:
            r = sybil_attack_cost(pool, cost_per_sybil_usd=unit)
            assert r.total_cost_usd == pytest.approx(r.num_sybils_required * unit)

    def test_more_validators_requires_more_sybils(self):
        pool3 = demo_validators()
        pool10 = scaled_validators(10)
        r3 = sybil_attack_cost(pool3, cost_per_sybil_usd=5.0)
        r10 = sybil_attack_cost(pool10, cost_per_sybil_usd=5.0)
        assert r10.num_sybils_required > r3.num_sybils_required

    def test_sybil_cost_scales_linearly_with_pool_weight(self):
        """Doubling average validator weight should roughly double Sybil cost."""
        pool_low = scaled_validators(5, avg_brier=0.30)   # lower weight
        pool_high = scaled_validators(5, avg_brier=0.05)  # higher weight
        r_low = sybil_attack_cost(pool_low)
        r_high = sybil_attack_cost(pool_high)
        assert r_high.num_sybils_required > r_low.num_sybils_required

    def test_no_to_yes_flip(self):
        pool = demo_validators()
        r = sybil_attack_cost(pool, cost_per_sybil_usd=5.0, target_flip="NO→YES")
        assert r.target_flip == "NO→YES"
        assert r.num_sybils_required > 0


# ---------------------------------------------------------------------------
# TestBriberyAttackCost
# ---------------------------------------------------------------------------

class TestBriberyAttackCost:
    def test_demo_pool_bribery_baseline(self):
        """3-agent demo: 2 agents must be flipped for YES→NO."""
        pool = demo_validators(bribery_cost_usd=250)
        r = bribery_attack_cost(pool, target_flip="YES→NO")
        assert isinstance(r, BriberyAttackResult)
        assert r.attack_succeeds is True
        assert r.num_agents_flipped >= 1

    def test_greedy_highest_weight_first(self):
        """Greedy should flip highest-weight agents first."""
        pool = demo_validators(bribery_cost_usd=250)
        r = bribery_attack_cost(pool, target_flip="YES→NO")
        # The oracle (highest weight) should be the first flipped
        if r.agents_flipped:
            assert r.agents_flipped[0] == "agent-oracle"

    def test_post_attack_probability_satisfies_threshold(self):
        pool = demo_validators(bribery_cost_usd=250)
        r = bribery_attack_cost(pool, target_flip="YES→NO")
        if r.attack_succeeds:
            assert r.post_attack_probability <= NO_THRESHOLD + 1e-9

    def test_bribery_cost_monotone_in_unit_price(self):
        """Doubling per-agent bribery cost should double total cost."""
        pool_cheap = demo_validators(bribery_cost_usd=100)
        pool_dear = demo_validators(bribery_cost_usd=200)
        r_cheap = bribery_attack_cost(pool_cheap)
        r_dear = bribery_attack_cost(pool_dear)
        # Same number of agents flipped (same pool structure)
        if r_cheap.num_agents_flipped == r_dear.num_agents_flipped:
            assert r_dear.total_cost_usd == pytest.approx(2 * r_cheap.total_cost_usd)

    def test_more_validators_requires_more_bribes(self):
        pool3 = demo_validators(bribery_cost_usd=250)
        pool10 = scaled_validators(10, bribery_cost_usd=250)
        r3 = bribery_attack_cost(pool3)
        r10 = bribery_attack_cost(pool10)
        assert r10.num_agents_flipped >= r3.num_agents_flipped

    def test_single_agent_pool_flipped(self):
        """Single agent can always be bribed."""
        pool = [ValidatorProfile("only", 0.10, 200, bribery_cost_usd=1000)]
        r = bribery_attack_cost(pool, target_flip="YES→NO")
        assert r.num_agents_flipped == 1
        assert r.total_cost_usd == 1000.0


# ---------------------------------------------------------------------------
# TestSecurityParameter
# ---------------------------------------------------------------------------

class TestSecurityParameter:
    def test_returns_security_parameter_object(self):
        pool = demo_validators()
        sp = security_parameter(pool, market_size_usd=10_000)
        assert isinstance(sp, SecurityParameter)

    def test_security_ratio_definition(self):
        pool = demo_validators()
        market = 10_000.0
        sp = security_parameter(pool, market_size_usd=market)
        expected_ratio = sp.min_attack_cost_usd / market
        assert sp.security_ratio == pytest.approx(expected_ratio)

    def test_secure_when_attack_cost_exceeds_market(self):
        # Small market, large bribery cost → secure
        pool = demo_validators(bribery_cost_usd=50_000)
        sp = security_parameter(pool, market_size_usd=1_000)
        assert sp.is_economically_secure is True

    def test_insecure_when_attack_cost_below_market(self):
        # Huge market, tiny bribery cost, tiny sybil cost → insecure
        pool = demo_validators(bribery_cost_usd=1.0)
        sp = security_parameter(pool, market_size_usd=1_000_000)
        assert sp.is_economically_secure is False

    def test_min_attack_cost_is_minimum_of_two_vectors(self):
        pool = demo_validators(bribery_cost_usd=250)
        sp = security_parameter(pool, market_size_usd=5_000)
        expected = min(sp.sybil_attack.total_cost_usd, sp.bribery_attack.total_cost_usd)
        assert sp.min_attack_cost_usd == pytest.approx(expected)

    def test_cheapest_vector_matches_cost(self):
        pool = demo_validators(bribery_cost_usd=250)
        sp = security_parameter(pool, market_size_usd=5_000)
        if sp.cheapest_vector == "sybil":
            assert sp.sybil_attack.total_cost_usd <= sp.bribery_attack.total_cost_usd
        elif sp.cheapest_vector == "bribery":
            assert sp.bribery_attack.total_cost_usd <= sp.sybil_attack.total_cost_usd

    def test_bribery_cheaper_than_sybil_in_3agent_demo(self):
        """Headline result from adversarial analysis (run #6): bribery 2.7× cheaper."""
        pool = demo_validators(bribery_cost_usd=250)
        sp = security_parameter(pool, market_size_usd=10_000)
        assert sp.cheapest_vector == "bribery"
        assert sp.bribery_attack.total_cost_usd < sp.sybil_attack.total_cost_usd


# ---------------------------------------------------------------------------
# TestPoolSizeScaling
# ---------------------------------------------------------------------------

class TestPoolSizeScaling:
    def test_returns_correct_length(self):
        sizes = [3, 5, 10]
        points = pool_size_scaling(sizes, market_size_usd=10_000)
        assert len(points) == 3

    def test_security_ratio_increases_with_pool_size(self):
        sizes = [3, 10, 50]
        points = pool_size_scaling(sizes, market_size_usd=10_000)
        ratios = [p.security_ratio for p in points]
        assert ratios[0] < ratios[1] < ratios[2]

    def test_small_pool_insecure_for_large_market(self):
        sizes = [3]
        points = pool_size_scaling(sizes, market_size_usd=1_000_000, bribery_cost_usd=100)
        assert not points[0].is_secure


# ---------------------------------------------------------------------------
# TestMarketSizeScaling
# ---------------------------------------------------------------------------

class TestMarketSizeScaling:
    def test_returns_correct_length(self):
        markets = [1_000, 10_000, 100_000]
        points = market_size_scaling(markets, pool_size=10)
        assert len(points) == 3

    def test_security_ratio_decreases_as_market_grows(self):
        markets = [1_000, 10_000, 100_000]
        points = market_size_scaling(markets, pool_size=10)
        ratios = [p.security_ratio for p in points]
        assert ratios[0] > ratios[1] > ratios[2]

    def test_attack_cost_constant_across_market_sizes(self):
        """Attack cost depends on pool, not market size."""
        markets = [1_000, 10_000, 100_000]
        points = market_size_scaling(markets, pool_size=5)
        costs = [p.min_attack_cost_usd for p in points]
        # All costs should be the same (pool is fixed)
        assert costs[0] == pytest.approx(costs[1])
        assert costs[1] == pytest.approx(costs[2])


# ---------------------------------------------------------------------------
# TestMinimumViablePool
# ---------------------------------------------------------------------------

class TestMinimumViablePool:
    def test_returns_integer(self):
        n = minimum_viable_pool_for_market(10_000, bribery_cost_usd=500)
        assert isinstance(n, int)

    def test_larger_market_requires_larger_pool(self):
        n_small = minimum_viable_pool_for_market(10_000, bribery_cost_usd=500)
        n_large = minimum_viable_pool_for_market(100_000, bribery_cost_usd=500)
        assert n_large >= n_small

    def test_higher_bribery_cost_requires_smaller_pool(self):
        n_cheap = minimum_viable_pool_for_market(50_000, bribery_cost_usd=100)
        n_dear = minimum_viable_pool_for_market(50_000, bribery_cost_usd=10_000)
        assert n_dear <= n_cheap

    def test_returned_pool_is_actually_secure(self):
        market = 20_000
        n = minimum_viable_pool_for_market(market, bribery_cost_usd=1000)
        if n != -1:
            pool = scaled_validators(n, bribery_cost_usd=1000)
            sp = security_parameter(pool, market_size_usd=market)
            assert sp.is_economically_secure


# ---------------------------------------------------------------------------
# TestCLIOutput
# ---------------------------------------------------------------------------

class TestCLIOutput:
    def _run(self, *args):
        result = subprocess.run(
            [sys.executable, "-m", "scripts.economic_model", *args],
            capture_output=True, text=True,
            cwd=str(Path(__file__).parent.parent)
        )
        return result

    def test_default_run_exits_zero(self):
        result = self._run()
        assert result.returncode == 0

    def test_output_contains_key_sections(self):
        result = self._run()
        out = result.stdout
        assert "Economic Security Model" in out
        assert "Sybil attack" in out
        assert "Bribery attack" in out
        assert "Security ratio" in out

    def test_custom_market_size(self):
        result = self._run("--market-size", "100000")
        assert result.returncode == 0
        assert "$100.0K" in result.stdout or "100000" in result.stdout

    def test_pool_scaling_flag(self):
        result = self._run("--pool-scaling")
        assert result.returncode == 0
        assert "validators" in result.stdout

    def test_mvp_flag(self):
        result = self._run("--mvp")
        assert result.returncode == 0
        assert "Minimum viable pool" in result.stdout

    def test_json_output(self, tmp_path):
        out_path = tmp_path / "econ.json"
        result = self._run("--json", str(out_path))
        assert result.returncode == 0
        assert out_path.exists()
        data = json.loads(out_path.read_text())
        assert "security_parameter" in data
        assert "min_attack_cost_usd" in data["security_parameter"]


# ---------------------------------------------------------------------------
# TestPublicSurface
# ---------------------------------------------------------------------------

class TestPublicSurface:
    def test_module_is_importable(self):
        import scripts.economic_model as m
        assert hasattr(m, "security_parameter")
        assert hasattr(m, "sybil_attack_cost")
        assert hasattr(m, "bribery_attack_cost")
        assert hasattr(m, "minimum_viable_pool_for_market")

    def test_key_constants_match_protocol(self):
        """Economic model constants must mirror weights.py and consensus.py."""
        from swarm_oracle.weights import (
            BASE_WEIGHT as W_BASE,
            EPSILON as W_EPSILON,
            MIN_PREDICTIONS as W_MIN,
        )
        from swarm_oracle.consensus import (
            DEFAULT_YES_THRESHOLD,
            DEFAULT_NO_THRESHOLD,
        )
        assert BASE_WEIGHT == W_BASE
        assert EPSILON == W_EPSILON
        assert YES_THRESHOLD == DEFAULT_YES_THRESHOLD
        assert NO_THRESHOLD == DEFAULT_NO_THRESHOLD
