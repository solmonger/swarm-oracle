"""End-to-end integration tests — full pipeline in demo mode.

These tests exercise the complete Swarm Oracle pipeline without any LLM server:
  question → demo agents → weights → consensus → decision → on-chain bridge prep

No mocking. The demo mode provides deterministic agent responses, so we can
verify the entire flow from question to final output in one pass.
"""
from __future__ import annotations

import json
import subprocess
import sys

import pytest

from swarm_oracle.agent import default_swarm
from swarm_oracle.consensus import aggregate_consensus, AgentVote
from swarm_oracle.demo_mode import demo_run, demo_votes
from swarm_oracle.on_chain import verify_parity
from swarm_oracle.verifier import SwarmResult
from swarm_oracle.weights import (
    mock_brier_history,
    weights_from_history,
    compute_weight,
)


# ---------------------------------------------------------------------------
# Full pipeline: demo_run → consensus → verify
# ---------------------------------------------------------------------------


class TestFullPipeline:
    """Run the complete pipeline end-to-end in demo mode."""

    QUESTIONS = [
        "Did BTC close above $100K on May 5, 2026?",
        "Will the Lakers beat the Celtics tonight?",
        "Is climate change accelerating beyond 2°C projections?",
    ]

    def test_demo_run_returns_valid_swarm_result(self):
        for q in self.QUESTIONS:
            result = demo_run(q)
            assert isinstance(result, SwarmResult), f"Failed for: {q}"
            assert result.question == q
            assert result.consensus is not None
            assert result.consensus.decision in ("YES", "NO", "DISPUTE")
            assert 0.0 <= result.consensus.probability <= 1.0
            assert result.consensus.num_votes >= 2
            assert result.elapsed_seconds >= 0

    def test_demo_votes_produce_three_agents(self):
        for q in self.QUESTIONS:
            votes = demo_votes(q)
            assert len(votes) == 3
            ids = {v.agent_id for v in votes}
            assert ids == {"agent-oracle", "agent-reliable", "agent-novice"}

    def test_weights_are_consistent_with_history(self):
        history = mock_brier_history()
        weights = weights_from_history(history)
        # oracle has lowest brier → highest weight
        assert weights["agent-oracle"] > weights["agent-reliable"]
        assert weights["agent-reliable"] > weights["agent-novice"]

    def test_consensus_contributions_sum_to_one(self):
        for q in self.QUESTIONS:
            result = demo_run(q)
            total = sum(c.normalized_weight for c in result.consensus.contributions)
            assert abs(total - 1.0) < 0.01, f"Contributions sum to {total} for: {q}"

    def test_crypto_question_resolves_no(self):
        """Crypto demo questions use low probabilities → expect NO."""
        result = demo_run("Did BTC close above $100K on May 5, 2026?")
        # The oracle agent gives ~0.03, reliable ~0.05, novice ~0.50
        # Weighted consensus should be well below 0.15 → NO
        assert result.consensus.decision == "NO"
        assert result.consensus.probability < 0.15

    def test_variance_is_non_negative(self):
        for q in self.QUESTIONS:
            result = demo_run(q)
            assert result.consensus.variance >= 0.0

    def test_each_vote_has_evidence(self):
        """Oracle and reliable agents should have evidence; novice may not."""
        votes = demo_votes("Did BTC close above $100K on May 5, 2026?")
        vote_map = {v.agent_id: v for v in votes}
        assert len(vote_map["agent-oracle"].evidence) > 0
        assert len(vote_map["agent-reliable"].evidence) > 0

    def test_pipeline_reproducibility(self):
        """Demo mode is deterministic — same question should yield same result."""
        q = "Did BTC close above $100K on May 5, 2026?"
        r1 = demo_run(q)
        r2 = demo_run(q)
        assert r1.consensus.probability == r2.consensus.probability
        assert r1.consensus.decision == r2.consensus.decision


# ---------------------------------------------------------------------------
# On-chain bridge integration (mocked contract, real logic)
# ---------------------------------------------------------------------------


class TestOnChainBridgeIntegration:
    """Test the on-chain bridge logic with demo pipeline output."""

    @pytest.fixture
    def demo_result(self):
        return demo_run("Did BTC close above $100K on May 5, 2026?")

    def test_parity_check_passes_for_demo_result(self, demo_result):
        """verify_parity should confirm Python matches itself."""
        from contracts.bridge import OnChainResult
        on_chain = OnChainResult(
            question=demo_result.question,
            question_id=b'\x00' * 32,
            consensus_probability=demo_result.consensus.probability,
            decision=demo_result.consensus.decision,
            weighted_variance=demo_result.consensus.variance,
            num_votes=demo_result.consensus.num_votes,
            resolved_at=0,
            resolved=True,
        )
        report = verify_parity(demo_result, on_chain)
        assert report.within_tolerance is True
        assert report.decisions_match is True

    def test_parity_detects_mismatch(self, demo_result):
        """verify_parity should catch a decision mismatch."""
        from contracts.bridge import OnChainResult
        on_chain = OnChainResult(
            question=demo_result.question,
            question_id=b'\x00' * 32,
            consensus_probability=demo_result.consensus.probability,
            decision="YES",  # force mismatch
            weighted_variance=demo_result.consensus.variance,
            num_votes=demo_result.consensus.num_votes,
            resolved_at=0,
            resolved=True,
        )
        report = verify_parity(demo_result, on_chain)
        assert report.decisions_match is False


# ---------------------------------------------------------------------------
# CLI integration — subprocess
# ---------------------------------------------------------------------------


class TestCLIIntegration:
    """Run the CLI as a subprocess to test the full user-facing flow."""

    def test_cli_demo_text_output(self):
        result = subprocess.run(
            [sys.executable, "-m", "swarm_oracle", "--demo",
             "Did BTC close above $100K on May 5, 2026?"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0
        assert "SWARM ORACLE" in result.stdout
        assert "Consensus" in result.stdout or "Decision" in result.stdout

    def test_cli_demo_json_output(self):
        result = subprocess.run(
            [sys.executable, "-m", "swarm_oracle", "--demo", "--json",
             "Did BTC close above $100K on May 5, 2026?"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "consensus" in data
        assert data["consensus"]["decision"] in ("YES", "NO", "DISPUTE")
        assert "votes" in data
        assert len(data["votes"]) == 3

    def test_cli_demo_multiple_categories(self):
        """Verify demo mode handles all three question categories."""
        questions = [
            "Did ETH close above $3000?",      # crypto
            "Will the Lakers win tonight?",     # sports
            "Is AI progress accelerating?",     # general
        ]
        for q in questions:
            result = subprocess.run(
                [sys.executable, "-m", "swarm_oracle", "--demo", "--json", q],
                capture_output=True, text=True, timeout=30,
            )
            assert result.returncode == 0, f"CLI failed for: {q}\n{result.stderr}"
            data = json.loads(result.stdout)
            assert data["consensus"]["decision"] in ("YES", "NO", "DISPUTE")


# ---------------------------------------------------------------------------
# Weight math edge cases
# ---------------------------------------------------------------------------


class TestWeightEdgeCases:
    """Additional edge-case coverage for the weight formula."""

    def test_perfect_calibration_gets_max_weight(self):
        """Brier score near 0 → very high weight."""
        w = compute_weight(0.001, 200)
        # With brier=0.001 and epsilon=0.001: raw = 1/(0.001+0.001) = 500
        # Confidence at 200 predictions = 1.0 (capped)
        assert w > 100.0

    def test_terrible_calibration_gets_low_weight(self):
        """Brier score near 1.0 → weight near 1.0."""
        w = compute_weight(0.95, 200)
        assert w < 2.0

    def test_weight_monotonically_decreases_with_brier(self):
        """As Brier gets worse, weight should decrease."""
        briers = [0.01, 0.05, 0.10, 0.20, 0.50, 0.80]
        weights = [compute_weight(b, 200) for b in briers]
        for i in range(len(weights) - 1):
            assert weights[i] > weights[i + 1], (
                f"Weight should decrease: brier={briers[i]}→{weights[i]} "
                f"vs brier={briers[i+1]}→{weights[i+1]}"
            )

    def test_confidence_ramp_at_boundary(self):
        """At exactly CONFIDENCE_THRESHOLD predictions, confidence should be 1.0."""
        w_at = compute_weight(0.10, 100)
        w_above = compute_weight(0.10, 200)
        # Both should be equal since confidence caps at threshold
        assert abs(w_at - w_above) < 0.001


# ---------------------------------------------------------------------------
# Consensus edge cases
# ---------------------------------------------------------------------------


class TestConsensusEdgeCases:
    """Edge cases in consensus aggregation."""

    def test_unanimous_yes_gives_high_probability(self):
        votes = [
            AgentVote("a", 0.95, 0.9, [], "high yes", "test"),
            AgentVote("b", 0.92, 0.8, [], "high yes", "test"),
            AgentVote("c", 0.98, 0.9, [], "high yes", "test"),
        ]
        weights = {"a": 5.0, "b": 3.0, "c": 2.0}
        result = aggregate_consensus(votes, weights)
        assert result.decision == "YES"
        assert result.probability > 0.90

    def test_unanimous_no_gives_low_probability(self):
        votes = [
            AgentVote("a", 0.02, 0.9, [], "low", "test"),
            AgentVote("b", 0.05, 0.8, [], "low", "test"),
            AgentVote("c", 0.01, 0.9, [], "low", "test"),
        ]
        weights = {"a": 5.0, "b": 3.0, "c": 2.0}
        result = aggregate_consensus(votes, weights)
        assert result.decision == "NO"
        assert result.probability < 0.10

    def test_split_opinion_disputes(self):
        """When agents are sharply divided, expect DISPUTE."""
        votes = [
            AgentVote("a", 0.95, 0.9, [], "yes", "test"),
            AgentVote("b", 0.05, 0.9, [], "no", "test"),
        ]
        weights = {"a": 5.0, "b": 5.0}
        result = aggregate_consensus(votes, weights)
        # Equal-weight split: mean = 0.50, high variance → DISPUTE
        assert result.decision == "DISPUTE"

    def test_dominant_expert_overrides_novice(self):
        """High-weight expert should dominate the consensus."""
        votes = [
            AgentVote("expert", 0.95, 0.9, [], "yes", "test"),
            AgentVote("novice", 0.30, 0.3, [], "maybe", "test"),
        ]
        weights = {"expert": 100.0, "novice": 1.0}
        result = aggregate_consensus(votes, weights)
        # Expert's 100x weight should pull consensus near 0.95
        assert result.probability > 0.90
        assert result.decision == "YES"
