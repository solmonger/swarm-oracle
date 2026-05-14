"""CLI runner for the Sybil-resistance analysis.

Usage:

    python -m scripts.sybil_demo                    # default: YES target
    python -m scripts.sybil_demo --target NO        # NO target
    python -m scripts.sybil_demo --target DISPUTE   # DISPUTE target
    python -m scripts.sybil_demo --base-rate 0.3    # skewed base rate
    python -m scripts.sybil_demo --json out.json    # also write JSON
    python -m scripts.sybil_demo --all              # all three targets

Loads the canonical three-agent demo scenario from ``swarm_oracle.sybil``,
runs the security-margin computation, and prints a publication-grade
attack report. Exit code is 0 unless an invalid argument is supplied.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
from dataclasses import asdict
from typing import Iterable

from swarm_oracle import sybil as _sybil


_VALID_TARGETS = ("YES", "NO", "DISPUTE")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="sybil_demo",
        description=(
            "Compute the economic-security margin for the Swarm Oracle "
            "demo scenario against a Sybil attacker."
        ),
    )
    p.add_argument(
        "--target",
        choices=list(_VALID_TARGETS),
        default="YES",
        help="Decision the attacker wants the protocol to announce.",
    )
    p.add_argument(
        "--all",
        action="store_true",
        help="Run all three targets and print a combined report.",
    )
    p.add_argument(
        "--base-rate",
        type=float,
        default=0.5,
        help="Resolution base rate used to bound the constant-vote ceiling.",
    )
    p.add_argument(
        "--oracle-brier",
        type=float,
        default=0.10,
        help="Brier score of an oracle-tier agent (caps the comparison).",
    )
    p.add_argument(
        "--attacker-vote",
        type=float,
        default=None,
        help=(
            "Sybil vote (default: 1.0 for YES, 0.0 for NO, 0.5 for DISPUTE)."
        ),
    )
    p.add_argument(
        "--json",
        metavar="PATH",
        default=None,
        help="Also write the raw report to a JSON file at PATH.",
    )
    args = p.parse_args(argv)
    if not (0.0 <= args.base_rate <= 1.0):
        p.error(f"--base-rate {args.base_rate!r} must be in [0, 1]")
    if not (0.0 <= args.oracle_brier <= 1.0):
        p.error(f"--oracle-brier {args.oracle_brier!r} must be in [0, 1]")
    if args.attacker_vote is not None and not (
        0.0 <= args.attacker_vote <= 1.0
    ):
        p.error(f"--attacker-vote {args.attacker_vote!r} must be in [0, 1]")
    return args


def _build_scenario(
    target: str, attacker_vote: float | None
) -> _sybil.AttackScenario:
    base = _sybil.demo_scenario(target)  # type: ignore[arg-type]
    if attacker_vote is None:
        return base
    return _sybil.AttackScenario(
        honest_votes=base.honest_votes,
        honest_weights=base.honest_weights,
        target_decision=base.target_decision,
        attacker_vote=attacker_vote,
        yes_threshold=base.yes_threshold,
        no_threshold=base.no_threshold,
        variance_threshold=base.variance_threshold,
        default_weight=base.default_weight,
    )


def _margin_to_json_dict(margin: _sybil.SecurityMargin) -> dict:
    d = asdict(margin)
    # math.inf doesn't survive JSON round-trip cleanly; replace with a string
    # sentinel that's easy to grep for.
    for k, v in list(d.items()):
        if isinstance(v, float) and v == float("inf"):
            d[k] = "inf"
    return d


def _render_report(
    targets: Iterable[str],
    base_rate: float,
    oracle_brier: float,
    attacker_vote: float | None,
) -> tuple[str, list[dict]]:
    """Build the text + JSON report for one or more targets."""
    out_lines: list[str] = []
    json_records: list[dict] = []

    header = "Swarm Oracle — Sybil-Resistance Analysis"
    out_lines.append("=" * len(header))
    out_lines.append(header)
    out_lines.append("=" * len(header))
    out_lines.append("")
    out_lines.append(f"Base rate (assumed): {base_rate:.3f}")
    out_lines.append(f"Oracle Brier:        {oracle_brier:.3f}")
    if attacker_vote is not None:
        out_lines.append(f"Attacker vote:       {attacker_vote:.3f} (forced)")
    out_lines.append("")

    for target in targets:
        scenario = _build_scenario(target, attacker_vote)
        margin = _sybil.protocol_security_margin(
            scenario, base_rate=base_rate, oracle_brier=oracle_brier
        )
        section = f"--- Target: {target} ---"
        out_lines.append(section)
        out_lines.append(_sybil.format_margin_text(margin))
        out_lines.append("")
        json_records.append(
            {
                "target": target,
                **_margin_to_json_dict(margin),
            }
        )
    return "\n".join(out_lines).rstrip() + "\n", json_records


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    targets: tuple[str, ...] = (
        _VALID_TARGETS if args.all else (args.target,)
    )

    text, records = _render_report(
        targets=targets,
        base_rate=args.base_rate,
        oracle_brier=args.oracle_brier,
        attacker_vote=args.attacker_vote,
    )
    sys.stdout.write(text)

    if args.json:
        path = pathlib.Path(args.json)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w") as f:
            json.dump(records, f, indent=2)
            f.write("\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
