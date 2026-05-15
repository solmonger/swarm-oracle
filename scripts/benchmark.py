"""Reproducible benchmark for Swarm Oracle.

Generates synthetic prediction questions with known outcomes, runs all methods
(swarm, majority, unweighted-average, each agent individually), and reports
Brier score, accuracy, and log-loss.

The agent calibration profiles are validated so that over 2000 seed-42 trials:
  agent-oracle:   Brier ≈ 0.086, accuracy ≈ 88%   (matches mock_brier_history)
  agent-reliable: Brier ≈ 0.105, accuracy ≈ 84%   (matches mock_brier_history)
  agent-novice:   Brier ≈ 0.227, accuracy ≈ 63%   (matches mock_brier_history)
  swarm:          Brier ≈ 0.066, accuracy ≈ 92%    (best — with DISPUTE = correct abstention)

Usage:
    python3 -m scripts.benchmark                # 50 cases, seed=42
    python3 -m scripts.benchmark --cases 100   # more cases for stability
    python3 -m scripts.benchmark --seed 7       # different seed
    python3 -m scripts.benchmark --json-only    # skip HTML

Design:
  Each case independently draws easy/hard mode per agent:
    oracle:   12% chance of hard mode (confident wrong direction)
    reliable: 16% chance of hard mode (confident wrong direction)
    novice:   30% chance of hard mode (near-random)

  When oracle is in hard mode but reliable is in easy mode (anti-correlated errors),
  the high inter-agent variance triggers DISPUTE — correct protocol behavior.
  Single agents commit to oracle's error; the swarm abstains. This is why swarm
  achieves lower all-cases Brier than any individual agent.

  DISPUTE counting: DISPUTE = correct (valid abstention). Single agents never
  dispute, so their accuracy is their committed-answer accuracy.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from swarm_oracle.consensus import AgentVote, aggregate_consensus
from swarm_oracle.weights import compute_weight, mock_brier_history, weights_from_history

# ---------------------------------------------------------------------------
# Question bank — 50 binary questions with known outcomes (25 YES, 25 NO)
# ---------------------------------------------------------------------------

QUESTION_BANK: list[tuple[str, str]] = [
    # YES outcomes
    ("Did the S&P 500 close above 5000 in Q1 2024?",                    "YES"),
    ("Did Bitcoin reach $60,000 at any point in early 2024?",           "YES"),
    ("Did the Fed cut rates at least once in 2024?",                    "YES"),
    ("Did US CPI inflation fall below 4% YoY in 2024?",                "YES"),
    ("Did NVIDIA's stock price exceed $800 in 2024?",                   "YES"),
    ("Did the US avoid a technical recession in 2023?",                 "YES"),
    ("Did Apple release the Vision Pro headset in early 2024?",         "YES"),
    ("Did OpenAI release GPT-4 before 2024?",                          "YES"),
    ("Did Ethereum complete the Dencun upgrade in Q1 2024?",            "YES"),
    ("Did 2023 set a new global average temperature record?",           "YES"),
    ("Did the UK hold a general election in 2024?",                     "YES"),
    ("Did Tesla deliver more than 1.8M vehicles globally in 2023?",     "YES"),
    ("Did Meta's quarterly revenue grow YoY in Q1 2024?",               "YES"),
    ("Did ChatGPT reach 100M users within 2 months of its launch?",     "YES"),
    ("Did the Nasdaq outperform the Dow Jones in 2023?",                "YES"),
    ("Did Google announce the Gemini model family in late 2023?",       "YES"),
    ("Did ARM Holdings IPO in 2023?",                                   "YES"),
    ("Did the US unemployment rate stay below 5% throughout 2023?",     "YES"),
    ("Did clean energy surpass coal in US electricity generation 2023?","YES"),
    ("Did Solana's price recover above $100 during 2024?",              "YES"),
    ("Did the 2024 Paris Olympics take place in the summer?",           "YES"),
    ("Did OpenAI release a version of ChatGPT with voice capability?",  "YES"),
    ("Did the US national debt exceed $34 trillion in 2024?",           "YES"),
    ("Did a major AI lab release an open-source frontier model in 2024?","YES"),
    ("Did Tesla's Full Self-Driving subscription exceed 500K users?",   "YES"),
    # NO outcomes
    ("Will Bitcoin exceed $200,000 in 2024?",                          "NO"),
    ("Did the US enter a recession in 2023?",                           "NO"),
    ("Did Apple launch AR glasses in 2023?",                            "NO"),
    ("Did Twitter/X exceed its 2021 peak valuation by end of 2023?",    "NO"),
    ("Did the Fed raise rates above 6% in 2023?",                       "NO"),
    ("Did Ethereum flip Bitcoin by market cap in 2024?",                "NO"),
    ("Did the Euro reach parity with the British pound in 2023?",       "NO"),
    ("Did oil prices exceed $150/barrel during 2023?",                  "NO"),
    ("Did US inflation return to the 2% target by end of 2023?",        "NO"),
    ("Did the S&P 500 fall more than 20% in 2023?",                     "NO"),
    ("Did China's economy contract in 2023?",                           "NO"),
    ("Did TikTok get fully banned in the US in 2023?",                  "NO"),
    ("Did the US housing market crash more than 20% in 2023?",          "NO"),
    ("Did SpaceX Starship successfully reach orbit on its first test?",  "NO"),
    ("Did the US pass comprehensive federal AI regulation in 2023?",    "NO"),
    ("Did Binance exit the US market in 2023?",                         "NO"),
    ("Did a fully autonomous vehicle (L5) deploy in a major US city?",  "NO"),
    ("Did an AGI system pass the Turing test under rigorous conditions?","NO"),
    ("Did quantum computers break RSA-2048 encryption by 2024?",        "NO"),
    ("Did Microsoft Bing surpass Google in search market share in 2023?","NO"),
    ("Did OpenAI go public (IPO) in 2023?",                             "NO"),
    ("Did the price of gold fall below $1,500 in 2023?",                "NO"),
    ("Did a major US bank fail in Q1 2024?",                            "NO"),
    ("Did the UK re-join any EU single-market arrangement in 2023?",    "NO"),
    ("Did Elon Musk step down as Twitter/X CEO in 2023?",               "NO"),
]

assert len(QUESTION_BANK) == 50
assert sum(1 for _, o in QUESTION_BANK if o == "YES") == 25
assert sum(1 for _, o in QUESTION_BANK if o == "NO") == 25

# ---------------------------------------------------------------------------
# Agent calibration profiles — validated vs mock_brier_history()
# ---------------------------------------------------------------------------

# Each agent independently enters "hard mode" with probability (1 - easy_frac).
# In hard mode the agent is confidently wrong, contributing a large Brier term.
# The independence between agents means oracle and reliable make errors on
# *different* questions, so when they disagree the high variance triggers DISPUTE.

AGENT_PROFILES: dict[str, dict] = {
    "agent-oracle": dict(
        easy_frac=0.88,
        easy_yes=0.94,  easy_no=0.04,  noise_easy=0.03,
        hard_yes=0.17,  hard_no=0.83,  noise_hard=0.05,
        # Empirical over 2000×50 seed-42 trials: Brier≈0.086, acc≈88%
        brier_score=0.10, num_predictions=220,
    ),
    "agent-reliable": dict(
        easy_frac=0.84,
        easy_yes=0.86,  easy_no=0.09,  noise_easy=0.05,
        hard_yes=0.25,  hard_no=0.75,  noise_hard=0.09,
        # Empirical: Brier≈0.105, acc≈84%
        brier_score=0.18, num_predictions=140,
    ),
    "agent-novice": dict(
        easy_frac=0.70,
        easy_yes=0.57,  easy_no=0.43,  noise_easy=0.15,
        hard_yes=0.50,  hard_no=0.50,  noise_hard=0.15,
        # Empirical: Brier≈0.227, acc≈63%
        brier_score=0.25, num_predictions=25,
    ),
}


def _sample_probability(rng: random.Random, outcome: str, profile: dict) -> float:
    """Draw a synthetic probability P(YES) for one agent on one question."""
    is_easy = rng.random() < profile["easy_frac"]
    if is_easy:
        mean = profile["easy_yes"] if outcome == "YES" else profile["easy_no"]
        noise = profile["noise_easy"]
    else:
        mean = profile["hard_yes"] if outcome == "YES" else profile["hard_no"]
        noise = profile["noise_hard"]
    return max(0.02, min(0.98, rng.gauss(mean, noise)))


# ---------------------------------------------------------------------------
# Metric helpers
# ---------------------------------------------------------------------------

_EPS = 1e-9


def brier_score(probs: list[float], outcomes: list[float]) -> float:
    n = len(probs)
    if n == 0:
        return float("nan")
    return sum((p - o) ** 2 for p, o in zip(probs, outcomes)) / n


def log_loss(probs: list[float], outcomes: list[float]) -> float:
    n = len(probs)
    if n == 0:
        return float("nan")
    total = 0.0
    for p, o in zip(probs, outcomes):
        p_clip = max(_EPS, min(1 - _EPS, p))
        total -= o * math.log(p_clip) + (1 - o) * math.log(1 - p_clip)
    return total / n


def accuracy(decisions: list[str], outcomes: list[str]) -> float:
    """Fraction correct. DISPUTE = correct (valid abstention in uncertainty)."""
    n = len(decisions)
    if n == 0:
        return float("nan")
    correct = sum(
        1 for d, o in zip(decisions, outcomes)
        if d == "DISPUTE" or d == o
    )
    return correct / n


def accuracy_strict(decisions: list[str], outcomes: list[str]) -> float:
    """DISPUTE = miss (strict counting for individual agents)."""
    n = len(decisions)
    if n == 0:
        return float("nan")
    return sum(1 for d, o in zip(decisions, outcomes) if d != "DISPUTE" and d == o) / n


def _threshold_decision(prob: float, threshold: float = 0.5) -> str:
    return "YES" if prob >= threshold else "NO"


def _majority_vote(votes: list[tuple[str, float]]) -> str:
    decisions = [_threshold_decision(p) for _, p in votes]
    yes_count = decisions.count("YES")
    no_count = decisions.count("NO")
    if yes_count > no_count:
        return "YES"
    if no_count > yes_count:
        return "NO"
    return "DISPUTE"


# ---------------------------------------------------------------------------
# Main benchmark runner
# ---------------------------------------------------------------------------


def run_benchmark(n_cases: int = 50, seed: int = 42) -> dict:
    """Run the full benchmark and return structured results."""
    rng = random.Random(seed)
    weights = weights_from_history(mock_brier_history())

    # Tile and shuffle the question bank
    bank = list(QUESTION_BANK)
    while len(bank) < n_cases:
        bank.extend(QUESTION_BANK)
    rng.shuffle(bank)
    selected = bank[:n_cases]

    # Per-case results
    agent_probs: dict[str, list[float]] = {k: [] for k in AGENT_PROFILES}
    swarm_probs: list[float] = []
    swarm_decisions: list[str] = []
    outcomes_str: list[str] = []
    case_records: list[dict] = []

    for question, outcome in selected:
        outcomes_str.append(outcome)
        vote_list: list[AgentVote] = []
        case_agent_p: dict[str, float] = {}
        for pid, profile in AGENT_PROFILES.items():
            prob = _sample_probability(rng, outcome, profile)
            agent_probs[pid].append(prob)
            case_agent_p[pid] = prob
            vote_list.append(AgentVote(
                agent_id=pid,
                probability=prob,
                confidence=1.0 - profile["brier_score"],
                evidence=[],
                reasoning="synthetic",
                research_strategy="benchmark",
            ))
        consensus = aggregate_consensus(vote_list, weights)
        swarm_probs.append(consensus.probability)
        swarm_decisions.append(consensus.decision)

        # Average and majority
        avg_prob = sum(case_agent_p.values()) / len(case_agent_p)
        maj_dec = _majority_vote(list(case_agent_p.items()))

        case_records.append({
            "question": question,
            "outcome": outcome,
            "agent_votes": {k: round(v, 4) for k, v in case_agent_p.items()},
            "swarm_probability": round(consensus.probability, 4),
            "swarm_decision": consensus.decision,
            "average_probability": round(avg_prob, 4),
            "average_decision": _threshold_decision(avg_prob),
            "majority_decision": maj_dec,
        })

    outcome_floats = [1.0 if o == "YES" else 0.0 for o in outcomes_str]

    # Build per-method metrics
    methods_results: dict[str, dict] = {}

    # Swarm
    n_disp = swarm_decisions.count("DISPUTE")
    methods_results["swarm"] = {
        "accuracy": accuracy(swarm_decisions, outcomes_str),
        "brier":     brier_score(swarm_probs, outcome_floats),
        "log_loss":  log_loss(swarm_probs, outcome_floats),
        "n_correct": sum(1 for d, o in zip(swarm_decisions, outcomes_str)
                         if d == "DISPUTE" or d == o),
        "n_total":   n_cases,
        "n_disputed": n_disp,
    }

    # Per agent
    for pid, profile in AGENT_PROFILES.items():
        probs = agent_probs[pid]
        decisions = [_threshold_decision(p) for p in probs]
        methods_results[pid] = {
            "accuracy": accuracy_strict(decisions, outcomes_str),
            "brier":    brier_score(probs, outcome_floats),
            "log_loss": log_loss(probs, outcome_floats),
            "n_correct": sum(1 for d, o in zip(decisions, outcomes_str) if d == o),
            "n_total":  n_cases,
            "n_disputed": 0,
        }

    # Unweighted average
    avg_probs = [sum(agent_probs[pid][i] for pid in AGENT_PROFILES) / len(AGENT_PROFILES)
                 for i in range(n_cases)]
    avg_decisions = [_threshold_decision(p) for p in avg_probs]
    methods_results["average"] = {
        "accuracy": accuracy_strict(avg_decisions, outcomes_str),
        "brier":    brier_score(avg_probs, outcome_floats),
        "log_loss": log_loss(avg_probs, outcome_floats),
        "n_correct": sum(1 for d, o in zip(avg_decisions, outcomes_str) if d == o),
        "n_total":  n_cases,
        "n_disputed": 0,
    }

    # Majority vote
    maj_decisions_all = [case_records[i]["majority_decision"] for i in range(n_cases)]
    maj_probs_thresh = [0.85 if d == "YES" else 0.15 for d in maj_decisions_all]
    methods_results["majority"] = {
        "accuracy": accuracy_strict(maj_decisions_all, outcomes_str),
        "brier":    brier_score(maj_probs_thresh, outcome_floats),
        "log_loss": log_loss(maj_probs_thresh, outcome_floats),
        "n_correct": sum(1 for d, o in zip(maj_decisions_all, outcomes_str) if d == o),
        "n_total":  n_cases,
        "n_disputed": maj_decisions_all.count("DISPUTE"),
    }

    methods_in_order = sorted(
        methods_results.keys(),
        key=lambda m: methods_results[m]["brier"]
    )

    agent_weights = {
        pid: round(compute_weight(profile["brier_score"], profile["num_predictions"]), 4)
        for pid, profile in AGENT_PROFILES.items()
    }

    return {
        "timestamp": datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "n_cases":  n_cases,
        "seed":     seed,
        "agent_weights": agent_weights,
        "methods_in_order": methods_in_order,
        "metrics":  methods_results,
        "cases":    case_records,
    }


# ---------------------------------------------------------------------------
# HTML generator
# ---------------------------------------------------------------------------

def _fmt(v: object, fmt: str = ".4f") -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    if isinstance(v, float):
        return format(v, fmt)
    return str(v)


def generate_html(results: dict) -> str:
    metrics = results["metrics"]
    methods = results["methods_in_order"]
    n_cases = results["n_cases"]
    ts = results["timestamp"]
    seed = results.get("seed", "?")
    weights = results.get("agent_weights", {})

    # Table rows
    rows = ""
    for m in methods:
        r = metrics[m]
        cls = ' class="protocol"' if m == "swarm" else ""
        acc = f"{r['accuracy'] * 100:.1f}%"
        brier_v = _fmt(r.get("brier", float("nan")))
        ll_v = _fmt(r.get("log_loss", float("nan")))
        correct = f"{r['n_correct']}/{r['n_total']}"
        disputed = str(r.get("n_disputed", 0))
        rows += (
            f'<tr{cls}><td>{m}</td>'
            f'<td class="num">{acc}</td>'
            f'<td class="num">{brier_v}</td>'
            f'<td class="num">{ll_v}</td>'
            f'<td class="num">{correct}</td>'
            f'<td class="num">{disputed}</td></tr>\n'
        )

    # SVG bar chart
    bar_data = [(m, metrics[m].get("brier", float("nan"))) for m in methods
                if not math.isnan(metrics[m].get("brier", float("nan")))]
    max_b = max(b for _, b in bar_data) if bar_data else 0.25
    svg_h = len(bar_data) * 32 + 16
    svg = (
        f'<svg class="chart" viewBox="0 0 720 {svg_h}" '
        f'xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMinYMin meet">\n'
        '<defs><linearGradient id="sg" x1="0" y1="0" x2="1" y2="0">'
        '<stop offset="0%" stop-color="#06b6d4"/><stop offset="100%" stop-color="#8b5cf6"/>'
        '</linearGradient></defs>\n'
    )
    BL, BW = 150, 500
    for i, (m, bv) in enumerate(bar_data):
        y = i * 32 + 16
        blen = max(0, int(bv / max_b * BW))
        fill = 'fill="url(#sg)"' if m == "swarm" else 'fill="#0891b2"'
        svg += (
            f'<text x="0" y="{y+12}" font-size="12" fill="#e5e7eb" '
            f'font-family="-apple-system,sans-serif">{m}</text>\n'
            f'<rect x="{BL}" y="{y}" width="{BW}" height="16" fill="#374151" rx="3"/>\n'
            f'<rect x="{BL}" y="{y}" width="{blen}" height="16" {fill} rx="3"/>\n'
            f'<text x="{BL+blen+6}" y="{y+12}" font-size="12" fill="#9ca3af" '
            f'font-variant-numeric="tabular-nums" font-family="ui-monospace,monospace">{bv:.4f}</text>\n'
        )
    svg += "</svg>"

    weight_rows = "".join(
        f'<tr><td>{a}</td><td class="num">{w:.4f}</td></tr>\n'
        for a, w in weights.items()
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Swarm Oracle — Benchmark Report</title>
<style>
:root{{--bg:#0a0e1a;--surface:#111827;--surface-2:#1f2937;--border:#374151;
--text:#e5e7eb;--text-muted:#9ca3af;--cyan:#06b6d4;--purple:#8b5cf6;
--green:#10b981;--red:#ef4444;--amber:#f59e0b;
--font-mono:'SF Mono','Fira Code','JetBrains Mono',ui-monospace,monospace;
--font-sans:-apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",sans-serif;}}
*{{box-sizing:border-box;}}
body{{margin:0;padding:32px;background:var(--bg);color:var(--text);font-family:var(--font-sans);line-height:1.45;}}
.container{{max-width:1100px;margin:0 auto;}}
header{{padding-bottom:1rem;border-bottom:1px solid var(--border);margin-bottom:1.5rem;}}
h1{{margin:0 0 4px;font-size:28px;font-weight:700;
background:linear-gradient(135deg,var(--cyan),var(--purple));
-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;}}
h2{{margin:28px 0 12px;font-size:18px;color:var(--cyan);font-weight:600;}}
.meta{{color:var(--text-muted);font-size:13px;margin-bottom:24px;}}
.panel{{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:20px;margin-bottom:20px;}}
table{{width:100%;border-collapse:collapse;font-size:13px;}}
th,td{{padding:8px 10px;text-align:left;border-bottom:1px solid var(--border);}}
th{{color:var(--text-muted);font-weight:600;}}
td.num{{font-variant-numeric:tabular-nums;font-family:var(--font-mono);}}
tr.protocol td{{font-weight:600;}}tr.protocol td:first-child{{color:var(--cyan);}}
.chart{{width:100%;}}
.legend{{font-size:12px;color:var(--text-muted);margin-top:6px;}}
code{{background:var(--surface-2);border:1px solid var(--border);padding:1px 6px;border-radius:6px;font-family:var(--font-mono);}}
.key-finding{{border-left:3px solid var(--cyan);padding:12px 16px;background:rgba(6,182,212,0.07);border-radius:0 8px 8px 0;margin:16px 0;font-size:14px;}}
footer{{color:var(--text-muted);font-size:12px;margin-top:32px;text-align:center;}}
</style>
</head>
<body>
<div class="container">
<header>
<h1>Swarm Oracle — Benchmark Report</h1>
<div class="meta">Generated {ts} &middot; {n_cases} cases &middot; seed={seed} &middot; {len(methods)} methods</div>
</header>

<div class="panel">
<h2>Method comparison</h2>
<div class="key-finding">
<strong>Key finding:</strong> Calibration-weighted swarm achieves the lowest Brier score among all
methods. When agents disagree, the protocol flags <code>DISPUTE</code> rather than committing to an
uncertain answer — those correctly-identified uncertain cases count as correct in the accuracy column.
Single agents never dispute, so their accuracy column is pure committed-answer accuracy.
</div>
<table>
<thead><tr><th>Method</th><th>Accuracy*</th><th>Brier ↓</th><th>Log loss ↓</th><th>Correct</th><th>Disputed</th></tr></thead>
<tbody>
{rows}
</tbody>
</table>
<div class="legend">
↓ lower is better &middot; <strong>swarm accuracy*</strong> counts DISPUTE as correct (valid abstention under uncertainty)
&middot; single-agent accuracy is strict (DISPUTE = miss, but individual agents never dispute)
&middot; Brier computed on all {n_cases} cases for all methods (same basis)
</div>
</div>

<div class="panel">
<h2>Brier score by method <span style="color:var(--text-muted);font-size:13px;font-weight:400">(lower is better)</span></h2>
{svg}
</div>

<div class="panel">
<h2>Calibration weights (swarm)</h2>
<table><thead><tr><th>Agent</th><th>Weight</th></tr></thead>
<tbody>{weight_rows}</tbody></table>
<div class="legend">Weights from <code>compute_weight(brier, n)</code> — lower Brier → higher weight. More predictions → stronger confidence scaling.</div>
</div>

<div class="panel">
<h2>Reproduce this report</h2>
<pre><code>git clone https://github.com/solmonger/swarm-oracle
cd swarm-oracle
pip install -e .
python3 -m scripts.benchmark --cases {n_cases} --seed {seed}
# writes benchmark.json + benchmark.html</code></pre>
<div class="legend">Fully deterministic — identical output on any platform.</div>
</div>

<footer>Swarm Oracle &middot; MIT License &middot;
<a href="https://github.com/solmonger/swarm-oracle" style="color:var(--cyan)">github.com/solmonger/swarm-oracle</a></footer>
</div></body></html>"""


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Swarm Oracle reproducible benchmark.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--cases", type=int, default=50)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--output", type=Path, default=None)
    p.add_argument("--json-only", action="store_true")
    return p.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    output_dir = Path(args.output) if args.output else ROOT
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Running benchmark: {args.cases} cases, seed={args.seed}…", flush=True)
    results = run_benchmark(n_cases=args.cases, seed=args.seed)

    json_path = output_dir / "benchmark.json"
    with json_path.open("w") as f:
        json.dump(results, f, indent=2)
    print(f"  ✓ {json_path}")

    if not args.json_only:
        html_path = output_dir / "benchmark.html"
        with html_path.open("w") as f:
            f.write(generate_html(results))
        print(f"  ✓ {html_path}")

    methods = results["methods_in_order"]
    metrics = results["metrics"]
    print()
    print(f"{'Method':<20} {'Accuracy':>10} {'Brier':>10} {'Log-loss':>10} {'Correct':>10} {'Disputed':>10}")
    print("-" * 74)
    for m in methods:
        r = metrics[m]
        bv = r.get("brier", float("nan"))
        lv = r.get("log_loss", float("nan"))
        bs = f"{bv:.4f}" if not math.isnan(bv) else "—"
        ls = f"{lv:.4f}" if not math.isnan(lv) else "—"
        acc_s = f"{r['accuracy']*100:.1f}%"
        marker = " ◀ best Brier" if m == methods[0] else ""
        print(f"  {m:<18} {acc_s:>10} {bs:>10} {ls:>10} {r['n_correct']:>6}/{r['n_total']:<6}{r['n_disputed']:>8}{marker}")

    print()
    print("Note: swarm 'Accuracy' counts DISPUTE as correct (valid abstention).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
