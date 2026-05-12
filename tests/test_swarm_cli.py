"""Tests for swarm_oracle.cli — wiring of agents + weights + verifier."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from swarm_oracle import cli  # noqa: E402
from swarm_oracle.agent import SwarmAgent  # noqa: E402


def stub_agent(agent_id: str, probability: float):
    def llm(prompt: str, *, temperature: float = 0.3) -> str:
        return json.dumps(
            {"probability": probability, "confidence": 0.85, "reasoning": "stub"}
        )
    return SwarmAgent(
        agent_id=agent_id,
        system_prompt="x",
        research_strategy="none",
        llm_call=llm,
        research_fn=lambda q: [],
    )


def test_run_swarm_uses_mock_brier_history():
    """run_swarm wires mock_brier_history → weights → verify_question."""
    agents = [stub_agent("agent-oracle", 0.92), stub_agent("agent-reliable", 0.88), stub_agent("agent-novice", 0.5)]
    result = cli.run_swarm("Did X happen?", agents=agents)
    # All three default-named agents should have weights derived from history.
    contrib_ids = {c.agent_id for c in result.consensus.contributions}
    assert {"agent-oracle", "agent-reliable", "agent-novice"} == contrib_ids
    # agent-oracle has the lowest mock Brier → highest weight.
    by_id = {c.agent_id: c for c in result.consensus.contributions}
    assert by_id["agent-oracle"].weight > by_id["agent-novice"].weight


def test_format_result_text_contains_required_sections(capsys):
    agents = [stub_agent("agent-oracle", 0.95)]
    result = cli.run_swarm(
        "Did Bitcoin close above $100K on May 5?",
        agents=agents,
        weights_override={"agent-oracle": 1.0},
    )
    text = cli.format_result(result)
    assert "Question" in text
    assert "Consensus" in text
    assert "Decision" in text
    assert "agent-oracle" in text


def test_main_smoke_with_stub_agents(monkeypatch, capsys):
    """End-to-end main() with stub agents — no LLM call, exits 0."""
    agents = [stub_agent("a", 0.9), stub_agent("b", 0.95), stub_agent("c", 0.92)]
    monkeypatch.setattr(cli, "default_swarm", lambda: agents)
    rc = cli.main(["did x happen?"])
    captured = capsys.readouterr()
    assert rc == 0
    assert "DECISION" in captured.out.upper() or "Decision" in captured.out
    assert "agent-oracle" not in captured.out  # since we monkeypatched default_swarm
    assert "a" in captured.out
