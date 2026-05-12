"""Comprehensive tests for swarm_oracle.on_chain — bridge integration module.

Run with:
    cd ~/openclaw-infra && PYTHONPATH=. python3 -m pytest tests/test_on_chain.py -v
"""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from swarm_oracle.consensus import AgentVote, ConsensusResult, Contribution
from swarm_oracle.on_chain import (
    ParityReport,
    load_agent_registry,
    seed_from_forecast_db,
    seed_historical_brier,
    submit_result,
    verify_parity,
)
from swarm_oracle.verifier import SwarmResult

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

SAMPLE_REGISTRY = {
    "agent-oracle": "0x1111111111111111111111111111111111111111",
    "agent-reliable": "0x2222222222222222222222222222222222222222",
    "agent-novice": "0x3333333333333333333333333333333333333333",
}


def _make_swarm_result(
    question: str = "Will BTC hit 200K?",
    votes: list[tuple[str, float]] | None = None,
    probability: float = 0.72,
    decision: str = "DISPUTE",
) -> SwarmResult:
    """Build a realistic SwarmResult without running any LLM."""
    if votes is None:
        votes = [
            ("agent-oracle", 0.80),
            ("agent-reliable", 0.65),
            ("agent-novice", 0.70),
        ]

    agent_votes = [
        AgentVote(
            agent_id=aid,
            probability=prob,
            confidence=0.8,
            evidence=[],
            reasoning="stub",
            research_strategy="none",
        )
        for aid, prob in votes
    ]

    contributions = [
        Contribution(
            agent_id=aid,
            probability=prob,
            weight=1.0,
            normalized_weight=1.0 / len(votes),
        )
        for aid, prob in votes
    ]

    consensus = ConsensusResult(
        probability=probability,
        decision=decision,
        num_votes=len(votes),
        contributions=contributions,
        variance=0.004,
        dispute_reason=None,
    )

    return SwarmResult(
        question=question,
        votes=agent_votes,
        consensus=consensus,
        elapsed_seconds=0.1,
    )


def _make_on_chain_result(
    question: str = "Will BTC hit 200K?",
    probability: float = 0.72,
    decision: str = "DISPUTE",
):
    """Build a mock OnChainResult."""
    from contracts.bridge import OnChainResult

    return OnChainResult(
        question=question,
        question_id=b"\x00" * 32,
        consensus_probability=probability,
        decision=decision,
        weighted_variance=0.004,
        num_votes=3,
        resolved_at=0,
        resolved=True,
    )


def _make_mock_bridge(
    on_chain_probability: float = 0.72,
    on_chain_decision: str = "DISPUTE",
    question: str = "Will BTC hit 200K?",
) -> MagicMock:
    """Return a MagicMock SwarmBridge with preset get_result behaviour."""
    bridge = MagicMock()
    bridge.get_result.return_value = _make_on_chain_result(
        question=question,
        probability=on_chain_probability,
        decision=on_chain_decision,
    )
    receipt = MagicMock()
    receipt.transactionHash = b"\xab" * 32
    bridge.submit_votes.return_value = receipt
    bridge.seed_brier.return_value = receipt
    return bridge


# ---------------------------------------------------------------------------
# 1. test_load_agent_registry
# ---------------------------------------------------------------------------


def test_load_agent_registry(tmp_path):
    """Loads JSON from disk and returns correct mapping."""
    reg_file = tmp_path / "agent_registry.json"
    reg_file.write_text(json.dumps(SAMPLE_REGISTRY))

    registry = load_agent_registry(path=reg_file)

    assert registry == SAMPLE_REGISTRY
    assert registry["agent-oracle"] == "0x1111111111111111111111111111111111111111"
    assert len(registry) == 3


# ---------------------------------------------------------------------------
# 2. test_load_agent_registry_missing_file
# ---------------------------------------------------------------------------


def test_load_agent_registry_missing_file(tmp_path):
    """Raises FileNotFoundError when the registry file does not exist."""
    missing = tmp_path / "nonexistent.json"
    with pytest.raises(FileNotFoundError, match="Agent registry not found"):
        load_agent_registry(path=missing)


# ---------------------------------------------------------------------------
# 3. test_load_agent_registry_default_path
# ---------------------------------------------------------------------------


def test_load_agent_registry_default_path():
    """Default path resolves to contracts/agent_registry.json and loads fine."""
    registry = load_agent_registry()
    assert "agent-oracle" in registry
    assert "agent-reliable" in registry
    assert "agent-novice" in registry


# ---------------------------------------------------------------------------
# 4. test_submit_result_maps_agents
# ---------------------------------------------------------------------------


def test_submit_result_maps_agents():
    """submit_result passes correct addresses and probabilities to bridge."""
    bridge = _make_mock_bridge()
    result = _make_swarm_result(
        votes=[
            ("agent-oracle", 0.80),
            ("agent-reliable", 0.65),
            ("agent-novice", 0.70),
        ]
    )

    on_chain = submit_result(result, bridge, registry=SAMPLE_REGISTRY)

    # Verify submit_votes was called once with correct args.
    bridge.submit_votes.assert_called_once()
    call_kwargs = bridge.submit_votes.call_args

    # Positional or keyword — handle both.
    args, kwargs = call_kwargs
    submitted_question = kwargs.get("question") or args[0]
    submitted_agents = kwargs.get("agents") or args[1]
    submitted_probs = kwargs.get("probabilities") or args[2]

    assert submitted_question == result.question
    assert submitted_agents == [
        "0x1111111111111111111111111111111111111111",
        "0x2222222222222222222222222222222222222222",
        "0x3333333333333333333333333333333333333333",
    ]
    assert submitted_probs == pytest.approx([0.80, 0.65, 0.70])

    # get_result should be called to read back.
    bridge.get_result.assert_called_once_with(result.question)

    # Return value is the OnChainResult.
    assert on_chain.consensus_probability == pytest.approx(0.72)


# ---------------------------------------------------------------------------
# 5. test_submit_result_missing_agent
# ---------------------------------------------------------------------------


def test_submit_result_missing_agent():
    """Raises ValueError when an agent_id has no address mapping."""
    bridge = _make_mock_bridge()
    result = _make_swarm_result(
        votes=[("agent-oracle", 0.8), ("agent-unknown", 0.5)]
    )

    with pytest.raises(ValueError, match="agent-unknown"):
        submit_result(result, bridge, registry=SAMPLE_REGISTRY)


# ---------------------------------------------------------------------------
# 6. test_verify_parity_pass
# ---------------------------------------------------------------------------


def test_verify_parity_pass():
    """within_tolerance=True when local and on-chain probabilities match closely."""
    result = _make_swarm_result(probability=0.72, decision="DISPUTE")
    on_chain = _make_on_chain_result(probability=0.7205, decision="DISPUTE")

    report = verify_parity(result, on_chain, tolerance=0.01)

    assert report.within_tolerance is True
    assert report.decisions_match is True
    assert report.probability_delta == pytest.approx(abs(0.72 - 0.7205))
    assert "PASS" in report.details


# ---------------------------------------------------------------------------
# 7. test_verify_parity_fail
# ---------------------------------------------------------------------------


def test_verify_parity_fail():
    """within_tolerance=False when delta exceeds tolerance."""
    result = _make_swarm_result(probability=0.72, decision="DISPUTE")
    on_chain = _make_on_chain_result(probability=0.60, decision="DISPUTE")

    report = verify_parity(result, on_chain, tolerance=0.01)

    assert report.within_tolerance is False
    assert report.probability_delta == pytest.approx(abs(0.72 - 0.60))
    assert "FAIL" in report.details


# ---------------------------------------------------------------------------
# 8. test_verify_parity_decision_mismatch
# ---------------------------------------------------------------------------


def test_verify_parity_decision_mismatch():
    """decisions_match=False even when probabilities are within tolerance."""
    result = _make_swarm_result(probability=0.90, decision="YES")
    # On-chain computed a slightly different probability but different decision.
    on_chain = _make_on_chain_result(probability=0.905, decision="DISPUTE")

    report = verify_parity(result, on_chain, tolerance=0.01)

    assert report.within_tolerance is True
    assert report.decisions_match is False
    assert report.local_decision == "YES"
    assert report.on_chain_decision == "DISPUTE"
    # Details should flag the mismatch.
    assert "WARN" in report.details or "differ" in report.details


# ---------------------------------------------------------------------------
# 9. test_seed_historical_brier
# ---------------------------------------------------------------------------


def test_seed_historical_brier():
    """seed_historical_brier calls bridge.seed_brier for every agent in history."""
    bridge = _make_mock_bridge()

    brier_history = {
        "agent-oracle": {"brier_score": 0.10, "num_predictions": 220},
        "agent-reliable": {"brier_score": 0.18, "num_predictions": 140},
        "agent-novice": {"brier_score": 0.25, "num_predictions": 25},
    }

    results = seed_historical_brier(bridge, SAMPLE_REGISTRY, brier_history)

    assert len(results) == 3
    assert bridge.seed_brier.call_count == 3

    agent_ids = {r["agent_id"] for r in results}
    assert agent_ids == {"agent-oracle", "agent-reliable", "agent-novice"}

    oracle_result = next(r for r in results if r["agent_id"] == "agent-oracle")
    assert oracle_result["address"] == SAMPLE_REGISTRY["agent-oracle"]
    assert oracle_result["brier"] == pytest.approx(0.10)
    assert oracle_result["n"] == 220
    assert oracle_result["tx_hash"] is not None


def test_seed_historical_brier_skips_unmapped_agents():
    """Agents not in registry are silently skipped (logged, not raised)."""
    bridge = _make_mock_bridge()
    brier_history = {
        "agent-oracle": {"brier_score": 0.10, "num_predictions": 50},
        "agent-ghost": {"brier_score": 0.20, "num_predictions": 30},
    }

    results = seed_historical_brier(bridge, SAMPLE_REGISTRY, brier_history)

    # Only oracle should be seeded; ghost is not in registry.
    assert len(results) == 1
    assert results[0]["agent_id"] == "agent-oracle"
    assert bridge.seed_brier.call_count == 1


# ---------------------------------------------------------------------------
# 10. test_seed_from_forecast_db
# ---------------------------------------------------------------------------


def test_seed_from_forecast_db():
    """Reads resolved forecasts from sqlite, computes avg Brier, seeds on-chain."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        db_path = f.name

    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE forecasts (
            forecast_id TEXT PRIMARY KEY,
            model_id TEXT NOT NULL,
            brier_score REAL
        )
        """
    )
    # Three resolved forecasts for the same model.
    conn.executemany(
        "INSERT INTO forecasts VALUES (?, ?, ?)",
        [
            ("f1", "gemma4-26b", 0.08),
            ("f2", "gemma4-26b", 0.12),
            ("f3", "gemma4-26b", 0.10),
            ("f4", "gemma4-26b", None),  # unresolved — should be excluded
        ],
    )
    conn.commit()
    conn.close()

    bridge = _make_mock_bridge()
    results = seed_from_forecast_db(bridge, SAMPLE_REGISTRY, db_path)

    assert len(results) == 1
    assert results[0]["agent_id"] == "agent-oracle"
    assert results[0]["n"] == 3  # only 3 resolved rows
    # avg brier = (0.08 + 0.12 + 0.10) / 3 = 0.10
    assert results[0]["brier"] == pytest.approx(0.10, abs=1e-9)
    bridge.seed_brier.assert_called_once()


def test_seed_from_forecast_db_no_resolved(tmp_path):
    """Returns empty list when no resolved forecasts exist."""
    db_path = str(tmp_path / "empty.sqlite")
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE forecasts (forecast_id TEXT, model_id TEXT, brier_score REAL)"
    )
    conn.execute(
        "INSERT INTO forecasts VALUES ('f1', 'model-x', NULL)"
    )
    conn.commit()
    conn.close()

    bridge = _make_mock_bridge()
    results = seed_from_forecast_db(bridge, SAMPLE_REGISTRY, db_path)

    assert results == []
    bridge.seed_brier.assert_not_called()


# ---------------------------------------------------------------------------
# 11. test_end_to_end_flow
# ---------------------------------------------------------------------------


def test_end_to_end_flow():
    """Full submit_result → verify_parity flow with mock bridge."""
    question = "Will ETH hit 10K in 2026?"

    bridge = _make_mock_bridge(
        on_chain_probability=0.68,
        on_chain_decision="DISPUTE",
        question=question,
    )

    result = _make_swarm_result(
        question=question,
        votes=[
            ("agent-oracle", 0.70),
            ("agent-reliable", 0.65),
            ("agent-novice", 0.68),
        ],
        probability=0.675,
        decision="DISPUTE",
    )

    # Step 1: submit to chain.
    on_chain = submit_result(result, bridge, registry=SAMPLE_REGISTRY)
    assert on_chain.consensus_probability == pytest.approx(0.68)
    assert on_chain.decision == "DISPUTE"

    # Step 2: verify parity.
    report = verify_parity(result, on_chain, tolerance=0.01)

    # delta = |0.675 - 0.68| = 0.005 — within 0.01 tolerance.
    assert report.within_tolerance is True
    assert report.decisions_match is True
    assert report.probability_delta == pytest.approx(abs(0.675 - 0.68))

    # Step 3: sanity-check the bridge was called correctly.
    bridge.submit_votes.assert_called_once()
    bridge.get_result.assert_called_once_with(question)


# ---------------------------------------------------------------------------
# 12. test_parity_report_fields_are_correct
# ---------------------------------------------------------------------------


def test_parity_report_fields_are_correct():
    """All ParityReport fields are populated correctly."""
    result = _make_swarm_result(probability=0.55, decision="DISPUTE")
    on_chain = _make_on_chain_result(probability=0.56, decision="DISPUTE")

    report = verify_parity(result, on_chain, tolerance=0.02)

    assert isinstance(report, ParityReport)
    assert report.local_probability == pytest.approx(0.55)
    assert report.on_chain_probability == pytest.approx(0.56)
    assert report.probability_delta == pytest.approx(0.01)
    assert report.local_decision == "DISPUTE"
    assert report.on_chain_decision == "DISPUTE"
    assert report.decisions_match is True
    assert report.within_tolerance is True
    assert isinstance(report.details, str)
    assert len(report.details) > 0


# ---------------------------------------------------------------------------
# 13. test_submit_result_loads_registry_from_default_path
# ---------------------------------------------------------------------------


def test_submit_result_loads_registry_from_default_path():
    """submit_result auto-loads registry from default path when not provided."""
    bridge = _make_mock_bridge()
    result = _make_swarm_result(
        votes=[
            ("agent-oracle", 0.80),
            ("agent-reliable", 0.65),
            ("agent-novice", 0.70),
        ]
    )

    # Call without explicit registry — should load from contracts/agent_registry.json.
    on_chain = submit_result(result, bridge)

    bridge.submit_votes.assert_called_once()
    assert on_chain is not None
