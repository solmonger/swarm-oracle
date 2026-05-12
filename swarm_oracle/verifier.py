"""Multi-agent parallel verification orchestrator.

Fan a question out to N SwarmAgents in parallel, collect their AgentVotes,
and feed them to the consensus engine with a weight registry. Returns a
single `SwarmResult` capturing the question, every vote, and the consensus.

Defaults to a thread pool because the per-agent work is I/O-bound (LLM calls,
HTTP fetches). For deterministic test debugging, pass `max_workers=1`.
"""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Sequence

from .agent import SwarmAgent
from .consensus import (
    AgentVote,
    ConsensusResult,
    aggregate_consensus,
)

log = logging.getLogger("swarm_oracle.verifier")


@dataclass(frozen=True)
class SwarmResult:
    question: str
    votes: list[AgentVote]
    consensus: ConsensusResult
    elapsed_seconds: float


def verify_question(
    question: str,
    agents: Sequence[SwarmAgent],
    weights: dict[str, float],
    *,
    max_workers: int | None = None,
    yes_threshold: float | None = None,
    no_threshold: float | None = None,
) -> SwarmResult:
    """Run every agent against the question in parallel, then aggregate."""
    if not agents:
        raise ValueError("verify_question needs at least one agent")

    workers = max_workers if max_workers is not None else max(1, len(agents))

    t0 = time.perf_counter()
    votes = _run_agents(question, list(agents), workers)
    elapsed = time.perf_counter() - t0

    threshold_kwargs: dict = {}
    if yes_threshold is not None:
        threshold_kwargs["yes_threshold"] = yes_threshold
    if no_threshold is not None:
        threshold_kwargs["no_threshold"] = no_threshold

    consensus = aggregate_consensus(votes, weights, **threshold_kwargs)
    return SwarmResult(
        question=question,
        votes=votes,
        consensus=consensus,
        elapsed_seconds=elapsed,
    )


def _run_agents(
    question: str, agents: list[SwarmAgent], max_workers: int
) -> list[AgentVote]:
    """Execute agents in parallel; preserves caller order in the output."""
    if max_workers <= 1:
        return [_safe_verify(a, question) for a in agents]

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(_safe_verify, a, question) for a in agents]
        return [f.result() for f in futures]


def _safe_verify(agent: SwarmAgent, question: str) -> AgentVote:
    """Wrap agent.verify with a last-resort neutral fallback."""
    try:
        return agent.verify(question)
    except Exception as exc:  # noqa: BLE001
        log.warning("agent %s raised: %s", agent.agent_id, exc)
        return AgentVote(
            agent_id=agent.agent_id,
            probability=0.5,
            confidence=0.1,
            evidence=[],
            reasoning=f"NEUTRAL (agent raised: {exc})",
            research_strategy=agent.research_strategy,
        )
