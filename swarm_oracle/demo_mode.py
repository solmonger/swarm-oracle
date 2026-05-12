"""Demo mode — hardcoded realistic responses for recording without an LLM server.

Usage:
    python swarm_verify.py --demo "Did BTC close above $100K on May 5, 2026?"
    python swarm_verify.py --demo "Will ETH be above $3,000 on June 1, 2026?"

Provides three canned agent responses per question category (crypto, sports,
general) with realistic evidence, reasoning, and calibration-weighted output.
No network calls are made in demo mode.
"""
from __future__ import annotations

import time
import random
from .consensus import AgentVote, Evidence, ConsensusResult, Contribution


# ---------------------------------------------------------------------------
# Canned demo responses by question category
# ---------------------------------------------------------------------------

CRYPTO_DEMO = {
    "agent-oracle": AgentVote(
        agent_id="agent-oracle",
        probability=0.030,
        confidence=0.90,
        research_strategy="api",
        reasoning="CoinGecko API shows BTC at $81,224 as of May 12 — well below $100K. "
                  "30-day trend is +3.2% but would need a 23% surge to reach the target.",
        evidence=[
            Evidence(
                source="CoinGecko API",
                snippet="Bitcoin (BTC): $81,224.00 USD. 24h change: +1.4%. "
                        "30d change: +3.2%. Market cap: $1.61T. Volume: $28.4B.",
                timestamp="2026-05-12T10:30:00Z",
                source_type="api",
                confidence=0.95,
            ),
        ],
    ),
    "agent-reliable": AgentVote(
        agent_id="agent-reliable",
        probability=0.050,
        confidence=0.80,
        research_strategy="web_search",
        reasoning="Multiple sources confirm BTC trading around $81K. Analyst consensus "
                  "suggests resistance at $85K. No catalyst identified for a $100K breakout.",
        evidence=[
            Evidence(
                source="search:bitcoin price forecast",
                snippet="Bitcoin hovers near $81K as traders await Fed minutes. "
                        "Key resistance at $85K with support at $78K. Institutional "
                        "flows remain neutral after ETF rebalancing.",
                timestamp=None,
                source_type="web",
                confidence=0.60,
            ),
        ],
    ),
    "agent-novice": AgentVote(
        agent_id="agent-novice",
        probability=0.500,
        confidence=0.00,
        research_strategy="knowledge",
        reasoning="No real-time data available. Bitcoin has historically traded between "
                  "$60K-$110K in 2026. Cannot assess current price without evidence.",
        evidence=[],
    ),
}

SPORTS_DEMO = {
    "agent-oracle": AgentVote(
        agent_id="agent-oracle",
        probability=0.720,
        confidence=0.85,
        research_strategy="api",
        reasoning="Historical H2H record shows the favorite winning 7 of last 10 meetings. "
                  "Current form: W-W-D-W-L in last 5 matches.",
        evidence=[
            Evidence(
                source="Sports API",
                snippet="Head-to-head: 7W-1D-2L in last 10. Home team xG: 1.82. "
                        "Away team xG: 1.14. Odds: 1.65 / 3.80 / 5.50.",
                timestamp="2026-05-12T09:00:00Z",
                source_type="api",
                confidence=0.80,
            ),
        ],
    ),
    "agent-reliable": AgentVote(
        agent_id="agent-reliable",
        probability=0.650,
        confidence=0.70,
        research_strategy="web_search",
        reasoning="Pre-match analysis and recent form favor the home team but away side "
                  "has shown improved defensive structure in recent weeks.",
        evidence=[
            Evidence(
                source="search:match preview analysis",
                snippet="Expected tight contest. Home advantage significant in this "
                        "fixture historically. Key absences on both sides may affect outcome.",
                timestamp=None,
                source_type="web",
                confidence=0.55,
            ),
        ],
    ),
    "agent-novice": AgentVote(
        agent_id="agent-novice",
        probability=0.550,
        confidence=0.20,
        research_strategy="knowledge",
        reasoning="Without current season data, relying on general knowledge of the teams. "
                  "Slight lean toward the historically stronger side.",
        evidence=[],
    ),
}

GENERAL_DEMO = {
    "agent-oracle": AgentVote(
        agent_id="agent-oracle",
        probability=0.150,
        confidence=0.75,
        research_strategy="api",
        reasoning="Available data suggests the event is unlikely based on current trends "
                  "and historical base rates.",
        evidence=[
            Evidence(
                source="Data API",
                snippet="Historical base rate for this type of event: 12-18%. "
                        "No significant deviation detected in recent data.",
                timestamp="2026-05-12T10:00:00Z",
                source_type="api",
                confidence=0.70,
            ),
        ],
    ),
    "agent-reliable": AgentVote(
        agent_id="agent-reliable",
        probability=0.200,
        confidence=0.60,
        research_strategy="web_search",
        reasoning="Web sources indicate low probability. Multiple independent analyses "
                  "converge on the 15-25% range.",
        evidence=[
            Evidence(
                source="search:event analysis",
                snippet="Expert consensus places probability at 15-20%. Key factors: "
                        "historical precedent, current conditions, and trend analysis.",
                timestamp=None,
                source_type="web",
                confidence=0.55,
            ),
        ],
    ),
    "agent-novice": AgentVote(
        agent_id="agent-novice",
        probability=0.400,
        confidence=0.10,
        research_strategy="knowledge",
        reasoning="Insufficient information to make a strong assessment. "
                  "Defaulting toward uncertainty.",
        evidence=[],
    ),
}


def _detect_category(question: str) -> str:
    """Detect question category from keywords."""
    q = question.lower()
    crypto_kw = ["btc", "bitcoin", "eth", "ethereum", "sol", "solana", "crypto", "price"]
    sports_kw = ["win", "match", "game", "score", "team", "league", "cup", "vs"]
    if any(k in q for k in crypto_kw):
        return "crypto"
    if any(k in q for k in sports_kw):
        return "sports"
    return "general"


def demo_votes(question: str) -> list[AgentVote]:
    """Return canned agent votes appropriate for the question category."""
    category = _detect_category(question)
    demos = {
        "crypto": CRYPTO_DEMO,
        "sports": SPORTS_DEMO,
        "general": GENERAL_DEMO,
    }
    template = demos[category]
    # Return votes in a consistent order
    return [template["agent-oracle"], template["agent-reliable"], template["agent-novice"]]


def demo_run(question: str) -> "SwarmResult":
    """Run a full demo swarm with canned data and simulated timing."""
    from .verifier import SwarmResult
    from .weights import mock_brier_history, weights_from_history
    from .consensus import aggregate_consensus

    # Simulate realistic timing
    start = time.monotonic()
    time.sleep(random.uniform(0.8, 1.5))  # Simulate agent execution

    votes = demo_votes(question)
    weights = weights_from_history(mock_brier_history())
    consensus = aggregate_consensus(votes, weights)
    elapsed = time.monotonic() - start

    return SwarmResult(
        question=question,
        votes=votes,
        consensus=consensus,
        elapsed_seconds=round(elapsed, 2),
    )
