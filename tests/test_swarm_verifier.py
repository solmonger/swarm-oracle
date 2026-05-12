"""Tests for swarm_oracle.verifier — parallel multi-agent orchestrator."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from swarm_oracle import verifier as V  # noqa: E402
from swarm_oracle.agent import SwarmAgent  # noqa: E402
from swarm_oracle.consensus import AgentVote, ConsensusResult, Evidence  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers — agents with deterministic LLM stubs
# ---------------------------------------------------------------------------


def stub_agent(agent_id: str, probability: float, confidence: float = 0.8, delay: float = 0.0):
    """Build a SwarmAgent whose llm_call returns a fixed JSON response."""
    def llm(prompt: str, *, temperature: float = 0.3) -> str:
        if delay:
            time.sleep(delay)
        return json.dumps({"probability": probability, "confidence": confidence, "reasoning": "stub"})
    return SwarmAgent(
        agent_id=agent_id,
        system_prompt="stub",
        research_strategy="none",
        llm_call=llm,
        research_fn=lambda q: [],
    )


# ---------------------------------------------------------------------------
# verify_question — happy path
# ---------------------------------------------------------------------------


def test_verify_question_returns_swarm_result():
    agents = [stub_agent("a", 0.9), stub_agent("b", 0.95), stub_agent("c", 0.92)]
    weights = {"a": 1.0, "b": 1.0, "c": 1.0}
    result = V.verify_question("Did X happen?", agents, weights)
    assert isinstance(result, V.SwarmResult)
    assert isinstance(result.consensus, ConsensusResult)
    assert result.question == "Did X happen?"
    assert len(result.votes) == 3
    assert all(isinstance(v, AgentVote) for v in result.votes)
    assert result.consensus.decision == "YES"


def test_verify_question_fans_out_in_parallel():
    """3 agents at 0.5s delay each — parallel ≈ 0.5s, sequential would be 1.5s."""
    delay = 0.5
    agents = [stub_agent(f"a{i}", 0.7, delay=delay) for i in range(3)]
    weights = {f"a{i}": 1.0 for i in range(3)}

    t0 = time.perf_counter()
    V.verify_question("Q?", agents, weights)
    elapsed = time.perf_counter() - t0

    # Allow some scheduler slop — tighten only if flaky.
    assert elapsed < delay * 2, f"verify_question seemed sequential: {elapsed:.2f}s"


def test_verify_question_continues_when_one_agent_raises():
    """An agent throwing should not abort the whole swarm."""

    def boom(prompt: str, *, temperature: float = 0.3) -> str:
        raise RuntimeError("simulated failure")

    bad = SwarmAgent(
        agent_id="bad",
        system_prompt="x",
        research_strategy="none",
        llm_call=boom,
        research_fn=lambda q: [],
    )
    good = stub_agent("good", 0.92)
    weights = {"bad": 1.0, "good": 1.0}

    result = V.verify_question("Q?", [bad, good], weights)
    # Both votes are present — bad agent gets a neutral fallback vote.
    assert len(result.votes) == 2
    assert any(v.agent_id == "good" and v.probability == pytest.approx(0.92) for v in result.votes)
    bad_v = next(v for v in result.votes if v.agent_id == "bad")
    assert bad_v.probability == pytest.approx(0.5)
    assert bad_v.confidence <= 0.2


def test_verify_question_uses_weights_to_influence_consensus():
    agents = [stub_agent("a", 0.95), stub_agent("b", 0.05)]
    # Heavily weight a's YES vote
    weights = {"a": 10.0, "b": 1.0}
    result = V.verify_question("Q?", agents, weights)
    # Weighted mean = (10*0.95 + 1*0.05) / 11 ≈ 0.868
    assert result.consensus.probability > 0.85


def test_verify_question_empty_agents_raises():
    with pytest.raises(ValueError):
        V.verify_question("Q?", [], {})


# ---------------------------------------------------------------------------
# Concurrency cap
# ---------------------------------------------------------------------------


def test_verify_question_respects_max_workers():
    """If max_workers=1, runs sequentially — useful for shared-state debugging."""
    delay = 0.2
    agents = [stub_agent(f"a{i}", 0.7, delay=delay) for i in range(3)]
    weights = {f"a{i}": 1.0 for i in range(3)}

    t0 = time.perf_counter()
    V.verify_question("Q?", agents, weights, max_workers=1)
    elapsed = time.perf_counter() - t0

    # Sequential should take roughly 3 * 0.2 = 0.6s
    assert elapsed >= 0.5
