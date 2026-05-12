"""CLI for the Swarm Oracle Week-1 demo.

Usage:

    python -m swarm_oracle "Did BTC close above $100K on May 5, 2026?"
    python swarm_verify.py "..."   # symlink / wrapper

Wires together:
    1. The default agent fleet (3+ agents, ≥2 research strategies).
    2. Mock Brier history → calibration weights.
    3. The parallel verifier.
    4. A pretty-printed result with per-agent contributions, weights, and
       the final consensus decision.
"""
from __future__ import annotations

import argparse
import logging
import sys
from typing import Sequence

from .agent import SwarmAgent, default_swarm
from .verifier import SwarmResult, verify_question
from .weights import mock_brier_history, weights_from_history

log = logging.getLogger("swarm_oracle.cli")


# ---------------------------------------------------------------------------
# Wiring
# ---------------------------------------------------------------------------


def run_swarm(
    question: str,
    agents: Sequence[SwarmAgent] | None = None,
    weights_override: dict[str, float] | None = None,
) -> SwarmResult:
    """End-to-end: agents → weights → consensus."""
    agent_list = list(agents) if agents is not None else default_swarm()
    if weights_override is not None:
        weights = dict(weights_override)
    else:
        weights = weights_from_history(mock_brier_history())
    return verify_question(question, agent_list, weights)


# ---------------------------------------------------------------------------
# Pretty-print
# ---------------------------------------------------------------------------


def format_result(result: SwarmResult) -> str:
    lines: list[str] = []
    sep = "=" * 72

    lines.append(sep)
    lines.append("  SWARM ORACLE  |  Calibration-Weighted Consensus")
    lines.append(sep)
    lines.append(f"Question : {result.question}")
    lines.append(f"Agents   : {len(result.votes)}")
    lines.append(f"Elapsed  : {result.elapsed_seconds:.2f}s")
    lines.append("")

    # Per-agent breakdown
    lines.append("Individual votes:")
    by_id = {v.agent_id: v for v in result.votes}
    for c in sorted(
        result.consensus.contributions,
        key=lambda c: c.normalized_weight,
        reverse=True,
    ):
        v = by_id.get(c.agent_id)
        if v is None:
            continue
        bar = _bar(c.normalized_weight, width=20)
        lines.append(
            f"  {c.agent_id:<16} | strategy={v.research_strategy:<11} | "
            f"P(YES)={v.probability:.3f} | conf={v.confidence:.2f} | "
            f"weight={c.weight:6.2f} ({c.normalized_weight*100:5.1f}%) {bar}"
        )
        if v.reasoning:
            reasoning = v.reasoning.replace("\n", " ")
            if len(reasoning) > 220:
                reasoning = reasoning[:217] + "..."
            lines.append(f"      reasoning: {reasoning}")
        if v.evidence:
            for ev in v.evidence[:2]:
                snippet = ev.snippet.replace("\n", " ")
                if len(snippet) > 140:
                    snippet = snippet[:137] + "..."
                lines.append(
                    f"      evidence : [{ev.source_type}] {ev.source} → {snippet}"
                )
    lines.append("")

    # Consensus
    cons = result.consensus
    lines.append("Consensus:")
    lines.append(f"  Weighted P(YES) = {cons.probability:.4f}")
    lines.append(f"  Variance        = {cons.variance:.4f}")
    lines.append(f"  Decision        = {cons.decision}")
    if cons.dispute_reason:
        lines.append(f"  Note            = {cons.dispute_reason}")
    lines.append(sep)
    return "\n".join(lines)


def _bar(fraction: float, width: int = 20) -> str:
    fraction = max(0.0, min(1.0, fraction))
    filled = int(round(fraction * width))
    return "█" * filled + "·" * (width - filled)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="swarm_verify",
        description=(
            "Run the Swarm Oracle on a yes/no question. "
            "Spawns 3+ agents in parallel, weights their votes by mock "
            "calibration scores, and prints the consensus."
        ),
    )
    parser.add_argument("question", help="Yes/no question to verify (in quotes)")
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show debug logs"
    )
    parser.add_argument(
        "--json", action="store_true", help="Emit machine-readable JSON instead"
    )
    parser.add_argument(
        "--demo", action="store_true",
        help="Use canned responses (no LLM server needed) — for demo recordings",
    )
    parser.add_argument(
        "--on-chain", action="store_true", help="Submit votes on-chain after local consensus"
    )
    parser.add_argument("--rpc", default=None, help="RPC URL for on-chain submission")
    parser.add_argument(
        "--registry-addr", default=None, help="CalibrationRegistry contract address"
    )
    parser.add_argument(
        "--consensus-addr", default=None, help="SwarmConsensus contract address"
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        if args.demo:
            from .demo_mode import demo_run
            result = demo_run(args.question)
        else:
            result = run_swarm(args.question)
    except Exception as exc:  # noqa: BLE001
        print(f"swarm_oracle: failed to run swarm: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(_to_json(result))
    else:
        print(format_result(result))

    if args.on_chain:
        from .on_chain import load_agent_registry, submit_result, verify_parity

        try:
            from contracts.bridge import SwarmBridge
        except ImportError:
            print(
                "On-chain submission requires web3.py: pip install 'swarm-oracle[chain]'",
                file=sys.stderr,
            )
            return 1

        bridge = SwarmBridge(rpc_url=args.rpc)
        bridge.set_addresses(registry=args.registry_addr, consensus=args.consensus_addr)
        agent_reg = load_agent_registry()

        print("\nSubmitting votes on-chain...")
        on_chain_result = submit_result(result, bridge, agent_reg)

        parity = verify_parity(result, on_chain_result)
        print(f"On-chain consensus: {on_chain_result.consensus_probability:.4f}")
        print(f"Parity: {'PASS' if parity.within_tolerance else 'FAIL'} (delta={parity.probability_delta:.6f})")

    return 0


def _to_json(result: SwarmResult) -> str:
    import json as _json

    return _json.dumps(
        {
            "question": result.question,
            "elapsed_seconds": result.elapsed_seconds,
            "consensus": {
                "probability": result.consensus.probability,
                "decision": result.consensus.decision,
                "variance": result.consensus.variance,
                "dispute_reason": result.consensus.dispute_reason,
                "num_votes": result.consensus.num_votes,
            },
            "contributions": [
                {
                    "agent_id": c.agent_id,
                    "probability": c.probability,
                    "weight": c.weight,
                    "normalized_weight": c.normalized_weight,
                }
                for c in result.consensus.contributions
            ],
            "votes": [
                {
                    "agent_id": v.agent_id,
                    "probability": v.probability,
                    "confidence": v.confidence,
                    "research_strategy": v.research_strategy,
                    "reasoning": v.reasoning,
                    "evidence": [
                        {
                            "source": e.source,
                            "snippet": e.snippet,
                            "source_type": e.source_type,
                            "confidence": e.confidence,
                        }
                        for e in v.evidence
                    ],
                }
                for v in result.votes
            ],
        },
        indent=2,
    )


if __name__ == "__main__":
    raise SystemExit(main())
