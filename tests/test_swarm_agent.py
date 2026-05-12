"""Tests for swarm_oracle.agent — single-agent verification with Gemma4."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from swarm_oracle import agent as A  # noqa: E402
from swarm_oracle.consensus import AgentVote, Evidence  # noqa: E402


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


def fake_llm(json_payload: dict):
    """Returns a callable that mimics SwarmAgent's LLM call interface."""
    def _call(prompt: str, *, temperature: float = 0.3) -> str:
        return json.dumps(json_payload)
    return _call


def fake_research(evidence_list: list[Evidence]):
    def _research(question: str) -> list[Evidence]:
        return evidence_list
    return _research


# ---------------------------------------------------------------------------
# verify() — happy path
# ---------------------------------------------------------------------------


def test_verify_returns_agent_vote_with_correct_id():
    a = A.SwarmAgent(
        agent_id="agent-test",
        system_prompt="You are testy.",
        research_strategy="none",
        llm_call=fake_llm({"probability": 0.8, "confidence": 0.9, "reasoning": "because"}),
        research_fn=fake_research([]),
    )
    vote = a.verify("Did X happen?")
    assert isinstance(vote, AgentVote)
    assert vote.agent_id == "agent-test"
    assert vote.probability == pytest.approx(0.8)
    assert vote.confidence == pytest.approx(0.9)
    assert "because" in vote.reasoning
    assert vote.research_strategy == "none"


def test_verify_passes_evidence_into_vote():
    ev = Evidence(source="src", snippet="snip", source_type="api", confidence=0.95)
    a = A.SwarmAgent(
        agent_id="evid",
        system_prompt="x",
        research_strategy="api",
        llm_call=fake_llm({"probability": 0.5, "confidence": 0.5, "reasoning": "ok"}),
        research_fn=fake_research([ev]),
    )
    vote = a.verify("?")
    assert vote.evidence == [ev]


def test_verify_clamps_probability_to_unit_interval():
    """Model-emitted probability outside [0, 1] gets clamped, not rejected."""
    a = A.SwarmAgent(
        agent_id="clamp",
        system_prompt="x",
        research_strategy="none",
        llm_call=fake_llm({"probability": 1.7, "confidence": 0.5, "reasoning": "bad"}),
        research_fn=fake_research([]),
    )
    vote = a.verify("?")
    assert vote.probability == 1.0


def test_verify_clamps_negative_probability():
    a = A.SwarmAgent(
        agent_id="neg",
        system_prompt="x",
        research_strategy="none",
        llm_call=fake_llm({"probability": -0.2, "confidence": 0.5, "reasoning": "bad"}),
        research_fn=fake_research([]),
    )
    vote = a.verify("?")
    assert vote.probability == 0.0


def test_verify_handles_markdown_fences():
    """Mimic the existing forecaster's resilience to ```json fences."""
    def llm_with_fences(prompt: str, *, temperature: float = 0.3) -> str:
        return '```json\n{"probability": 0.42, "confidence": 0.7, "reasoning": "neutral"}\n```'

    a = A.SwarmAgent(
        agent_id="fence",
        system_prompt="x",
        research_strategy="none",
        llm_call=llm_with_fences,
        research_fn=fake_research([]),
    )
    vote = a.verify("?")
    assert vote.probability == pytest.approx(0.42)


def test_verify_falls_back_to_neutral_on_garbage_json():
    def garbage(prompt: str, *, temperature: float = 0.3) -> str:
        return "I refuse to comply with the format. Here is some text."

    a = A.SwarmAgent(
        agent_id="trash",
        system_prompt="x",
        research_strategy="none",
        llm_call=garbage,
        research_fn=fake_research([]),
    )
    vote = a.verify("?")
    # On unparseable output, return a neutral 0.5 vote with low confidence
    # rather than crashing the whole consensus run.
    assert vote.probability == pytest.approx(0.5)
    assert vote.confidence <= 0.2


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


def test_prompt_includes_evidence_snippets():
    captured = {}

    def capture(prompt: str, *, temperature: float = 0.3) -> str:
        captured["prompt"] = prompt
        return json.dumps({"probability": 0.5, "confidence": 0.5, "reasoning": "ok"})

    ev = Evidence(source="src1", snippet="UNIQUE_TOKEN_42", source_type="api", confidence=0.9)
    a = A.SwarmAgent(
        agent_id="p",
        system_prompt="You are P.",
        research_strategy="api",
        llm_call=capture,
        research_fn=fake_research([ev]),
    )
    a.verify("Did X happen?")
    assert "UNIQUE_TOKEN_42" in captured["prompt"]
    assert "Did X happen?" in captured["prompt"]
    assert "You are P." in captured["prompt"]


def test_prompt_handles_no_evidence():
    captured = {}

    def capture(prompt: str, *, temperature: float = 0.3) -> str:
        captured["prompt"] = prompt
        return json.dumps({"probability": 0.5, "confidence": 0.5, "reasoning": "ok"})

    a = A.SwarmAgent(
        agent_id="empty-evid",
        system_prompt="x",
        research_strategy="none",
        llm_call=capture,
        research_fn=fake_research([]),
    )
    a.verify("?")
    assert "no evidence" in captured["prompt"].lower() or "no relevant" in captured["prompt"].lower()


# ---------------------------------------------------------------------------
# Default agent factory
# ---------------------------------------------------------------------------


def test_default_swarm_returns_three_or_more_agents_with_distinct_ids():
    agents = A.default_swarm()
    assert len(agents) >= 3
    ids = [a.agent_id for a in agents]
    assert len(set(ids)) == len(ids)


def test_default_swarm_uses_at_least_two_research_strategies():
    agents = A.default_swarm()
    strategies = {a.research_strategy for a in agents}
    assert len(strategies) >= 2
