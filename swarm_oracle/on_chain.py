"""On-chain integration for the Swarm Oracle.

Bridges local Python consensus to on-chain contracts via bridge.py.
Three workflows:
1. submit_result() — post swarm consensus votes on-chain
2. verify_parity() — compare local vs on-chain consensus
3. seed_historical_brier() — populate on-chain registry from forecast DB
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from contracts.bridge import OnChainResult, SwarmBridge

    from .verifier import SwarmResult

# Default registry path: <repo-root>/contracts/agent_registry.json
_DEFAULT_REGISTRY_PATH = Path(__file__).parent.parent / "contracts" / "agent_registry.json"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ParityReport:
    """Comparison between local Python consensus and on-chain result."""

    local_probability: float
    on_chain_probability: float
    probability_delta: float
    local_decision: str
    on_chain_decision: str
    decisions_match: bool
    within_tolerance: bool
    details: str


# ---------------------------------------------------------------------------
# Registry loader
# ---------------------------------------------------------------------------


def load_agent_registry(path: str | Path | None = None) -> dict[str, str]:
    """Load agent_id → eth_address mapping from contracts/agent_registry.json.

    Args:
        path: Optional override path to registry JSON.
              Defaults to <repo-root>/contracts/agent_registry.json.

    Returns:
        Dict mapping agent_id strings to checksummed Ethereum addresses.

    Raises:
        FileNotFoundError: If the registry file does not exist.
    """
    registry_path = Path(path) if path is not None else _DEFAULT_REGISTRY_PATH
    if not registry_path.exists():
        raise FileNotFoundError(
            f"Agent registry not found at {registry_path}. "
            "Create contracts/agent_registry.json with agent_id → address mapping."
        )
    with registry_path.open() as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# On-chain submission
# ---------------------------------------------------------------------------


def submit_result(
    result: "SwarmResult",
    bridge: "SwarmBridge",
    registry: dict[str, str] | None = None,
) -> "OnChainResult":
    """Submit local swarm consensus votes to on-chain contracts.

    Maps each agent_id in the SwarmResult to an Ethereum address via
    the registry, then calls bridge.submit_votes() and reads back the
    on-chain result.

    Args:
        result:   SwarmResult from verify_question().
        bridge:   Configured SwarmBridge (addresses must be set).
        registry: agent_id → eth_address mapping. Loads from default
                  agent_registry.json if not provided.

    Returns:
        OnChainResult read back from the contract after submission.

    Raises:
        ValueError: If any agent_id in result.votes has no address mapping.
    """
    if registry is None:
        registry = load_agent_registry()

    agents: list[str] = []
    probabilities: list[float] = []

    for vote in result.votes:
        addr = registry.get(vote.agent_id)
        if addr is None:
            raise ValueError(
                f"Agent '{vote.agent_id}' has no address in registry. "
                f"Available agents: {sorted(registry.keys())}"
            )
        agents.append(addr)
        probabilities.append(vote.probability)

    bridge.submit_votes(
        question=result.question,
        agents=agents,
        probabilities=probabilities,
    )

    return bridge.get_result(result.question)


# ---------------------------------------------------------------------------
# Parity verification
# ---------------------------------------------------------------------------


def verify_parity(
    result: "SwarmResult",
    on_chain: "OnChainResult",
    tolerance: float = 0.01,
) -> ParityReport:
    """Compare local consensus probability with on-chain result.

    Args:
        result:    Local SwarmResult containing the Python-side consensus.
        on_chain:  OnChainResult read from the contract.
        tolerance: Maximum acceptable absolute delta between local and
                   on-chain probabilities. Default 0.01 (1 percentage point).

    Returns:
        ParityReport with comparison details and pass/fail flags.
    """
    local_prob = result.consensus.probability
    chain_prob = on_chain.consensus_probability
    delta = abs(local_prob - chain_prob)

    local_decision = result.consensus.decision
    chain_decision = on_chain.decision
    decisions_match = local_decision == chain_decision
    within_tolerance = delta <= tolerance

    if within_tolerance and decisions_match:
        details = (
            f"PASS — local={local_prob:.6f}, on-chain={chain_prob:.6f}, "
            f"delta={delta:.6f} ≤ tolerance={tolerance}"
        )
    elif within_tolerance and not decisions_match:
        details = (
            f"WARN — probabilities agree (delta={delta:.6f}) but decisions differ: "
            f"local={local_decision}, on-chain={chain_decision}"
        )
    else:
        details = (
            f"FAIL — delta={delta:.6f} exceeds tolerance={tolerance}. "
            f"local={local_prob:.6f}, on-chain={chain_prob:.6f}. "
            f"decisions: local={local_decision}, on-chain={chain_decision}"
        )

    return ParityReport(
        local_probability=local_prob,
        on_chain_probability=chain_prob,
        probability_delta=delta,
        local_decision=local_decision,
        on_chain_decision=chain_decision,
        decisions_match=decisions_match,
        within_tolerance=within_tolerance,
        details=details,
    )


# ---------------------------------------------------------------------------
# Brier seeding
# ---------------------------------------------------------------------------


def seed_historical_brier(
    bridge: "SwarmBridge",
    registry: dict[str, str],
    brier_history: dict[str, dict],
) -> list[dict]:
    """Seed on-chain CalibrationRegistry with historical Brier scores.

    Args:
        bridge:        Configured SwarmBridge.
        registry:      agent_id → eth_address mapping.
        brier_history: agent_id → {brier_score, num_predictions} as returned
                       by weights_from_history() or mock_brier_history().

    Returns:
        List of dicts: {agent_id, address, brier, n, tx_hash} for each seeded agent.
        Agents present in brier_history but missing from registry are skipped
        with a logged warning.
    """
    import logging

    log = logging.getLogger("swarm_oracle.on_chain")
    results = []

    for agent_id, entry in brier_history.items():
        address = registry.get(agent_id)
        if address is None:
            log.warning(
                "seed_historical_brier: agent '%s' not in registry — skipping",
                agent_id,
            )
            continue

        brier = float(entry.get("brier_score", 0.25))
        n = int(entry.get("num_predictions", 0))

        receipt = bridge.seed_brier(agent=address, brier=brier, num_predictions=n)

        tx_hash: str | None = None
        if receipt is not None:
            raw = getattr(receipt, "transactionHash", None)
            if raw is not None:
                tx_hash = raw.hex() if isinstance(raw, (bytes, bytearray)) else str(raw)

        results.append(
            {
                "agent_id": agent_id,
                "address": address,
                "brier": brier,
                "n": n,
                "tx_hash": tx_hash,
            }
        )

    return results


def seed_from_forecast_db(
    bridge: "SwarmBridge",
    registry: dict[str, str],
    db_path: str,
) -> list[dict]:
    """Compute per-agent average Brier from forecast DB and seed on-chain.

    Reads resolved forecasts (brier_score IS NOT NULL) from the SQLite
    forecast_events database, computes per-model_id average Brier and
    prediction count, maps model_id to agent_id (currently all map to
    "agent-oracle" as the default), then calls seed_historical_brier().

    Args:
        bridge:   Configured SwarmBridge.
        registry: agent_id → eth_address mapping.
        db_path:  Path to the forecast_events.sqlite database.

    Returns:
        Same list of dicts as seed_historical_brier().
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute(
            """
            SELECT
                model_id,
                AVG(brier_score)  AS avg_brier,
                COUNT(*)          AS num_predictions
            FROM forecasts
            WHERE brier_score IS NOT NULL
            GROUP BY model_id
            """
        )
        rows = cursor.fetchall()
    finally:
        conn.close()

    # Map model_id → agent_id.  Currently all forecasts come from one model
    # so we assign everything to "agent-oracle" as the default.
    brier_history: dict[str, dict] = {}
    for row in rows:
        # Use "agent-oracle" as the default agent for any model_id.
        agent_id = "agent-oracle"
        existing = brier_history.get(agent_id)
        if existing is None:
            brier_history[agent_id] = {
                "brier_score": row["avg_brier"],
                "num_predictions": row["num_predictions"],
            }
        else:
            # Merge if there are somehow multiple model rows mapping to same agent.
            total_n = existing["num_predictions"] + row["num_predictions"]
            merged_brier = (
                existing["brier_score"] * existing["num_predictions"]
                + row["avg_brier"] * row["num_predictions"]
            ) / total_n
            brier_history[agent_id] = {
                "brier_score": merged_brier,
                "num_predictions": total_n,
            }

    return seed_historical_brier(bridge, registry, brier_history)
