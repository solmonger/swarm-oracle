"""CLI demo for :mod:`swarm_oracle.adversarial`.

Runs the canonical 3-honest-agent scenario through the three attack
vectors (collusion, adaptive, bribery) and prints a publication-grade
report. Designed for ``make adversarial-demo`` and inline copy-paste
into hackathon submission materials.

Usage:
    python -m scripts.adversarial_demo                   # all three vectors
    python -m scripts.adversarial_demo --vector collusion
    python -m scripts.adversarial_demo --vector adaptive --num-sybils 4
    python -m scripts.adversarial_demo --vector bribery --bribery-cost 500
    python -m scripts.adversarial_demo --compare         # composed comparison
    python -m scripts.adversarial_demo --json out.json   # machine-readable
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from dataclasses import asdict, is_dataclass
from typing import Any

from swarm_oracle import adversarial as adv
from swarm_oracle import sybil


VECTOR_CHOICES = ("collusion", "adaptive", "bribery", "all")
TARGET_CHOICES = ("YES", "NO", "DISPUTE")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="adversarial_demo",
        description=(
            "Run multi-vector adversarial attack simulations against the "
            "Swarm Oracle protocol's calibration-weighted consensus."
        ),
    )
    parser.add_argument(
        "--vector",
        choices=VECTOR_CHOICES,
        default="all",
        help="Attack vector to simulate (default: all three).",
    )
    parser.add_argument(
        "--target",
        choices=TARGET_CHOICES,
        default="YES",
        help="Target decision the attacker is trying to force (default: YES).",
    )
    parser.add_argument(
        "--num-colluders",
        type=int,
        default=3,
        help="Number of colluding Sybils for the collusion vector (default: 3).",
    )
    parser.add_argument(
        "--num-sybils",
        type=int,
        default=4,
        help="Number of Sybils the adaptive attacker controls (default: 4).",
    )
    parser.add_argument(
        "--max-weight-per-sybil",
        type=float,
        default=100.0,
        help="Per-Sybil weight budget for the adaptive vector (default: 100.0).",
    )
    parser.add_argument(
        "--bribery-cost",
        type=float,
        default=adv.DEFAULT_BRIBERY_COST_USD,
        help=(
            "USD cost to flip one honest agent (default: "
            f"${adv.DEFAULT_BRIBERY_COST_USD:.0f})."
        ),
    )
    parser.add_argument(
        "--registry-cost",
        type=float,
        default=5.0,
        help="USD cost to register one Sybil agent for --compare (default: $5).",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Run a side-by-side Sybil-vs-bribery cost comparison.",
    )
    parser.add_argument(
        "--json",
        type=str,
        default=None,
        help="Write machine-readable JSON output to this path.",
    )

    args = parser.parse_args(argv)
    if args.num_colluders < 1:
        parser.error("--num-colluders must be ≥ 1")
    if args.num_sybils < 1:
        parser.error("--num-sybils must be ≥ 1")
    if args.max_weight_per_sybil < 0:
        parser.error("--max-weight-per-sybil must be ≥ 0")
    if args.bribery_cost < 0:
        parser.error("--bribery-cost must be ≥ 0")
    if args.registry_cost < 0:
        parser.error("--registry-cost must be ≥ 0")
    return args


def _scenario(args: argparse.Namespace) -> sybil.AttackScenario:
    return sybil.demo_scenario(args.target)


def _run_collusion(args: argparse.Namespace) -> tuple[str, dict[str, Any]]:
    scen = adv.CollusionScenario(
        base=_scenario(args), num_colluders=args.num_colluders
    )
    result = adv.simulate_collusion(scen)
    return adv.format_collusion_text(result), _result_to_jsonable(result)


def _run_adaptive(args: argparse.Namespace) -> tuple[str, dict[str, Any]]:
    scen = adv.AdaptiveScenario(
        base=_scenario(args),
        num_sybils=args.num_sybils,
        max_weight_per_sybil=args.max_weight_per_sybil,
    )
    result = adv.min_adaptive_weight(scen)
    return adv.format_adaptive_text(result), _result_to_jsonable(result)


def _run_bribery(args: argparse.Namespace) -> tuple[str, dict[str, Any]]:
    scen = adv.BriberyScenario(
        base=_scenario(args), cost_per_agent_usd=args.bribery_cost
    )
    result = adv.min_bribery_cost(scen)
    return adv.format_bribery_text(result), _result_to_jsonable(result)


def _run_compose(args: argparse.Namespace) -> tuple[str, dict[str, Any]]:
    composed = adv.compose_attacks(
        _scenario(args),
        registry_cost_usd=args.registry_cost,
        bribery_cost_usd=args.bribery_cost,
    )
    return adv.format_composed_text(composed), _result_to_jsonable(composed)


def _result_to_jsonable(result: Any) -> dict[str, Any]:
    """Convert a dataclass result to a JSON-serializable dict.

    ``math.inf`` and ``math.nan`` survive as the strings ``"inf"`` and
    ``"nan"`` — JSON has no native representation. Callers that re-parse
    can normalise with ``float()``.
    """
    if not is_dataclass(result):
        return {"value": str(result)}
    raw = asdict(result)
    return _scrub_floats(raw)


def _scrub_floats(value: Any) -> Any:
    if isinstance(value, float):
        if math.isinf(value):
            return "inf"
        if math.isnan(value):
            return "nan"
        return value
    if isinstance(value, dict):
        return {k: _scrub_floats(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub_floats(v) for v in value]
    return value


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    sections: list[tuple[str, str, dict[str, Any]]] = []

    if args.compare:
        text, data = _run_compose(args)
        sections.append(("compose", text, data))
    elif args.vector == "collusion":
        text, data = _run_collusion(args)
        sections.append(("collusion", text, data))
    elif args.vector == "adaptive":
        text, data = _run_adaptive(args)
        sections.append(("adaptive", text, data))
    elif args.vector == "bribery":
        text, data = _run_bribery(args)
        sections.append(("bribery", text, data))
    else:  # "all"
        sections.append(("collusion", *_run_collusion(args)))
        sections.append(("adaptive", *_run_adaptive(args)))
        sections.append(("bribery", *_run_bribery(args)))
        sections.append(("compose", *_run_compose(args)))

    # Always print text output to stdout
    print(
        "Swarm Oracle — Adversarial Simulation\n"
        "====================================="
    )
    print(f"Target decision: {args.target}\n")
    for _, text, _ in sections:
        print(text)
        print()

    if args.json is not None:
        parent = os.path.dirname(os.path.abspath(args.json))
        if parent:
            os.makedirs(parent, exist_ok=True)
        records = {name: data for name, _, data in sections}
        with open(args.json, "w") as f:
            json.dump(
                {
                    "target": args.target,
                    "results": records,
                },
                f,
                indent=2,
            )
        print(f"JSON output written to {args.json}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
