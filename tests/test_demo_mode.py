"""Tests for the --demo CLI flag and demo_mode module."""
from __future__ import annotations

import pytest
from swarm_oracle.demo_mode import demo_votes, demo_run, _detect_category


class TestDetectCategory:
    def test_crypto_btc(self):
        assert _detect_category("Did BTC close above $100K?") == "crypto"

    def test_crypto_ethereum(self):
        assert _detect_category("Will Ethereum be above $3000?") == "crypto"

    def test_sports_match(self):
        assert _detect_category("Will Barcelona win the match?") == "sports"

    def test_sports_game(self):
        assert _detect_category("T1 vs FearX game winner?") == "sports"

    def test_general_fallback(self):
        assert _detect_category("Will it rain tomorrow?") == "general"


class TestDemoVotes:
    def test_returns_three_agents(self):
        votes = demo_votes("Did BTC close above $100K?")
        assert len(votes) == 3

    def test_agent_ids(self):
        votes = demo_votes("Did BTC close above $100K?")
        ids = {v.agent_id for v in votes}
        assert ids == {"agent-oracle", "agent-reliable", "agent-novice"}

    def test_crypto_low_probability(self):
        """Crypto demo should show low P(YES) for oracle agent."""
        votes = demo_votes("Did BTC close above $100K?")
        oracle = [v for v in votes if v.agent_id == "agent-oracle"][0]
        assert oracle.probability < 0.1
        assert oracle.confidence > 0.5

    def test_sports_higher_probability(self):
        """Sports demo should show moderate-high P(YES) for oracle agent."""
        votes = demo_votes("Will the team win the match?")
        oracle = [v for v in votes if v.agent_id == "agent-oracle"][0]
        assert oracle.probability > 0.5

    def test_novice_always_low_confidence(self):
        for q in ["BTC price?", "Match winner?", "Will it rain?"]:
            votes = demo_votes(q)
            novice = [v for v in votes if v.agent_id == "agent-novice"][0]
            assert novice.confidence <= 0.2

    def test_evidence_present_for_oracle(self):
        votes = demo_votes("Did BTC close above $100K?")
        oracle = [v for v in votes if v.agent_id == "agent-oracle"][0]
        assert len(oracle.evidence) > 0

    def test_no_evidence_for_novice(self):
        votes = demo_votes("Did BTC close above $100K?")
        novice = [v for v in votes if v.agent_id == "agent-novice"][0]
        assert len(novice.evidence) == 0


class TestDemoRun:
    def test_returns_swarm_result(self):
        result = demo_run("Did BTC close above $100K?")
        assert result.question == "Did BTC close above $100K?"
        assert len(result.votes) == 3
        assert result.consensus is not None
        assert result.elapsed_seconds > 0

    def test_consensus_has_decision(self):
        result = demo_run("Did BTC close above $100K?")
        assert result.consensus.decision in ("YES", "NO", "DISPUTE")

    def test_consensus_probability_range(self):
        result = demo_run("Did BTC close above $100K?")
        assert 0.0 <= result.consensus.probability <= 1.0

    def test_contributions_sum_to_one(self):
        result = demo_run("Did BTC close above $100K?")
        total = sum(c.normalized_weight for c in result.consensus.contributions)
        assert abs(total - 1.0) < 0.01


class TestCLIDemoFlag:
    def test_demo_flag_runs_without_llm(self):
        """The --demo flag should work without any LLM server running."""
        from swarm_oracle.cli import main
        import io
        import contextlib

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = main(["--demo", "Did BTC close above $100K on May 5, 2026?"])
        assert rc == 0
        output = buf.getvalue()
        assert "SWARM ORACLE" in output
        assert "Consensus:" in output
        assert "agent-oracle" in output

    def test_demo_json_output(self):
        """--demo --json should produce valid JSON."""
        import json
        from swarm_oracle.cli import main
        import io
        import contextlib

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = main(["--demo", "--json", "Did BTC close above $100K?"])
        assert rc == 0
        data = json.loads(buf.getvalue())
        assert "consensus" in data
        assert "votes" in data
        assert len(data["votes"]) == 3
