"""Economic security model for the Swarm Oracle protocol.

Computes the minimum attack cost (Sybil and bribery) as a function of:

  - validator pool size N and their calibration weights
  - per-agent bribery cost B (USD)
  - per-Sybil registration cost C_reg (USD)
  - target market size M (USD)

The key output is a *security parameter* — the ratio of minimum attack cost
to market value.  When that ratio exceeds 1, the protocol is economically
secure for markets up to that size.

Usage::

    python3 -m scripts.economic_model
    python3 -m scripts.economic_model --market-size 100000
    python3 -m scripts.economic_model --market-size 1000000 --validators 20
    python3 -m scripts.economic_model --validators 10 --bribery-cost 1000 --json out.json

All amounts are in USD.  Protocol parameters (weights, thresholds) default to
the live Swarm Oracle constants from swarm_oracle/weights.py and
swarm_oracle/consensus.py.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Protocol constants — must mirror weights.py and consensus.py exactly.
# ---------------------------------------------------------------------------

BASE_WEIGHT = 1.0            # weight for new agents (< MIN_PREDICTIONS)
MIN_PREDICTIONS = 20         # predictions before calibration kicks in
CONFIDENCE_THRESHOLD = 100   # predictions where confidence reaches 1.0
EPSILON = 1e-3               # Brier smoothing constant
YES_THRESHOLD = 0.85         # consensus probability ≥ this → YES
NO_THRESHOLD = 0.15          # consensus probability ≤ this → NO
VARIANCE_THRESHOLD = 0.20    # std-dev above which → DISPUTE regardless


# ---------------------------------------------------------------------------
# Weight formula (mirrors compute_weight from weights.py)
# ---------------------------------------------------------------------------

def compute_weight(brier_score: float, num_predictions: int) -> float:
    """Calibration weight for one agent.

    Formula (design doc):
        if n < MIN_PREDICTIONS: return BASE_WEIGHT
        raw = 1 / (brier + EPSILON)
        confidence = min(1, n / CONFIDENCE_THRESHOLD)
        return raw * confidence
    """
    if num_predictions < MIN_PREDICTIONS:
        return BASE_WEIGHT
    raw = 1.0 / (brier_score + EPSILON)
    confidence = min(1.0, num_predictions / CONFIDENCE_THRESHOLD)
    return raw * confidence


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ValidatorProfile:
    """One honest validator in the pool."""
    agent_id: str
    brier_score: float
    num_predictions: int
    bribery_cost_usd: float  # cost to bribe this specific agent

    @property
    def weight(self) -> float:
        return compute_weight(self.brier_score, self.num_predictions)


@dataclass
class SybilAttackResult:
    """Result of computing the minimum Sybil attack cost."""
    num_sybils_required: int
    total_sybil_weight: float
    honest_total_weight: float
    sybil_weight_needed: float
    total_cost_usd: float
    cost_per_sybil_usd: float
    target_flip: str            # "YES→NO" or "NO→YES"
    attack_succeeds: bool
    note: str = ""


@dataclass
class BriberyAttackResult:
    """Result of computing the minimum bribery attack cost."""
    agents_flipped: list[str]
    num_agents_flipped: int
    total_cost_usd: float
    post_attack_probability: float
    attack_succeeds: bool
    target_flip: str
    note: str = ""


@dataclass
class SecurityParameter:
    """Composite security metric for a given market configuration."""
    market_size_usd: float
    min_attack_cost_usd: float
    cheapest_vector: str        # "sybil" | "bribery" | "both_equal"
    security_ratio: float       # min_attack_cost / market_size  (>1 = secure)
    is_economically_secure: bool
    sybil_attack: SybilAttackResult
    bribery_attack: BriberyAttackResult
    validator_pool_size: int
    note: str = ""


@dataclass
class ScalingPoint:
    """One row in the security-vs-pool-size or security-vs-market-size table."""
    variable: str
    value: float
    min_attack_cost_usd: float
    security_ratio: float
    is_secure: bool


# ---------------------------------------------------------------------------
# Core attack models
# ---------------------------------------------------------------------------

def sybil_attack_cost(
    validators: list[ValidatorProfile],
    cost_per_sybil_usd: float = 5.0,
    target_flip: str = "YES→NO",
) -> SybilAttackResult:
    """Compute the minimum number of Sybil agents and their total cost to flip
    a YES consensus to NO (or vice versa).

    Attack model:
    - The attacker registers k new agents, each with BASE_WEIGHT (no history).
    - New agents vote opposite to honest majority.
    - Consensus flips when weighted-average P(YES) crosses the threshold.

    For YES → NO:
        Honest agents all vote YES (P=1.0), total weight W_h.
        Sybils vote NO (P=0.0), total Sybil weight W_s.
        Consensus P(YES) = W_h / (W_h + W_s)  [ignoring variance gate]
        Attack succeeds when P(YES) ≤ NO_THRESHOLD.
        Required W_s ≥ W_h × (1/NO_THRESHOLD - 1) = W_h × (1-0.15)/0.15 = W_h × 5.667

    Each Sybil contributes BASE_WEIGHT = 1.0, so:
        k = ceil(W_s / BASE_WEIGHT)

    Note: this ignores the variance gate, which may trigger DISPUTE before the
    probability threshold is crossed.  The variance gate is a bonus defence,
    not a substitute for having sufficient honest weight.
    """
    honest_total_weight = sum(v.weight for v in validators)

    if target_flip == "YES→NO":
        # Need P(YES) ≤ 0.15
        # W_h / (W_h + W_s) ≤ 0.15
        # W_s ≥ W_h × (1/0.15 - 1)
        ratio = (1.0 - NO_THRESHOLD) / NO_THRESHOLD     # ≈ 5.667
        target_label = "YES→NO"
    else:
        # Need P(YES) ≥ 0.85
        # W_s / (W_h + W_s) ≥ 0.85
        # W_s ≥ W_h × 0.85 / 0.15 = W_h × 5.667
        ratio = YES_THRESHOLD / (1.0 - YES_THRESHOLD)   # ≈ 5.667
        target_label = "NO→YES"

    sybil_weight_needed = honest_total_weight * ratio
    k = math.ceil(sybil_weight_needed / BASE_WEIGHT)
    total_cost = k * cost_per_sybil_usd

    return SybilAttackResult(
        num_sybils_required=k,
        total_sybil_weight=k * BASE_WEIGHT,
        honest_total_weight=honest_total_weight,
        sybil_weight_needed=sybil_weight_needed,
        total_cost_usd=total_cost,
        cost_per_sybil_usd=cost_per_sybil_usd,
        target_flip=target_label,
        attack_succeeds=True,  # given sufficient budget
        note=(
            f"Requires ≥{sybil_weight_needed:.1f} Sybil weight "
            f"= {k} Sybils × BASE_WEIGHT={BASE_WEIGHT}"
        ),
    )


def bribery_attack_cost(
    validators: list[ValidatorProfile],
    target_flip: str = "YES→NO",
) -> BriberyAttackResult:
    """Compute the minimum bribery cost to flip the consensus.

    Attack model:
    - The attacker bribes m honest validators to vote opposite to their
      honest vote.  A bribed YES voter votes NO (P=0.0) and vice versa.
    - Greedy: bribe highest-weight validators first (cheapest per unit
      of probability mass moved).

    For YES → NO with N honest validators voting YES:
        Start: P(YES) ≈ 1.0 (all honest vote YES)
        Each validator i we bribe shifts their contribution from
          +w_i (YES) to -w_i (NO) — a swing of 2×w_i in the numerator.
        After bribing validators in set S:
          P(YES) = (W_total - 2 × sum_{i in S} w_i) / W_total

        Attack succeeds when P(YES) ≤ NO_THRESHOLD.

    This is a strict upper bound: the variance gate may DISPUTE earlier,
    helping the attacker even more in edge cases.
    """
    # Sort by weight descending (greedy: bribe high-weight agents first)
    sorted_validators = sorted(validators, key=lambda v: v.weight, reverse=True)

    total_weight = sum(v.weight for v in validators)

    # Determine the success condition
    if target_flip == "YES→NO":
        success_p = NO_THRESHOLD   # P(YES) ≤ 0.15
        flip_label = "YES→NO"
    else:
        success_p = YES_THRESHOLD  # P(YES) ≥ 0.85
        flip_label = "NO→YES"

    # Initial probability assuming all honest validators vote in the majority direction
    # (honest agents vote 1.0 for YES / 0.0 for NO in the flipped scenario)
    # For YES→NO: initial P = 1.0, bribed agents go from 1.0 to 0.0
    current_prob = 1.0 if target_flip == "YES→NO" else 0.0
    flipped_ids: list[str] = []
    flipped_weight = 0.0
    total_bribery_cost = 0.0

    for v in sorted_validators:
        if target_flip == "YES→NO":
            if current_prob <= success_p:
                break
            # Bribe this agent: they switch from voting YES (1.0) to NO (0.0)
            # New prob = (W_total × prob - w_i × 1.0 - (0.0 - 1.0) × w_i … )
            # Simpler: each bribed agent's contribution flips sign
            flipped_weight += v.weight
            # After bribe: numerator loses w_i (was YES) + gains -w_i (now NO)
            # net change in weighted-sum = -2 * w_i
            current_prob = max(0.0, (total_weight - 2 * flipped_weight) / total_weight)
        else:
            if current_prob >= success_p:
                break
            flipped_weight += v.weight
            current_prob = min(1.0, (total_weight - 2 * (total_weight - flipped_weight)) / total_weight)
            current_prob = max(0.0, flipped_weight / total_weight)

        flipped_ids.append(v.agent_id)
        total_bribery_cost += v.bribery_cost_usd

    success = (
        (target_flip == "YES→NO" and current_prob <= NO_THRESHOLD) or
        (target_flip == "NO→YES" and current_prob >= YES_THRESHOLD)
    )

    return BriberyAttackResult(
        agents_flipped=flipped_ids,
        num_agents_flipped=len(flipped_ids),
        total_cost_usd=total_bribery_cost,
        post_attack_probability=current_prob,
        attack_succeeds=success,
        target_flip=flip_label,
        note=(
            f"Flipped {len(flipped_ids)} agent(s) — "
            f"post-attack P(YES) = {current_prob:.4f}"
        ),
    )


def security_parameter(
    validators: list[ValidatorProfile],
    market_size_usd: float,
    cost_per_sybil_usd: float = 5.0,
    target_flip: str = "YES→NO",
) -> SecurityParameter:
    """Compute the composite security parameter for a given market configuration."""
    sybil = sybil_attack_cost(validators, cost_per_sybil_usd, target_flip)
    bribery = bribery_attack_cost(validators, target_flip)

    min_cost = min(sybil.total_cost_usd, bribery.total_cost_usd)
    if sybil.total_cost_usd < bribery.total_cost_usd:
        cheapest = "sybil"
    elif bribery.total_cost_usd < sybil.total_cost_usd:
        cheapest = "bribery"
    else:
        cheapest = "both_equal"

    ratio = min_cost / market_size_usd if market_size_usd > 0 else float("inf")
    secure = min_cost > market_size_usd

    return SecurityParameter(
        market_size_usd=market_size_usd,
        min_attack_cost_usd=min_cost,
        cheapest_vector=cheapest,
        security_ratio=ratio,
        is_economically_secure=secure,
        sybil_attack=sybil,
        bribery_attack=bribery,
        validator_pool_size=len(validators),
        note=(
            f"Security ratio {ratio:.3f}× "
            + ("(SECURE)" if secure else "(INSECURE — attack cheaper than prize)")
        ),
    )


# ---------------------------------------------------------------------------
# Validator-pool generators
# ---------------------------------------------------------------------------

def demo_validators(bribery_cost_usd: float = 250.0) -> list[ValidatorProfile]:
    """The 3-agent demo pool matching the hackathon benchmark."""
    return [
        ValidatorProfile("agent-oracle",   brier_score=0.10, num_predictions=220, bribery_cost_usd=bribery_cost_usd),
        ValidatorProfile("agent-reliable", brier_score=0.18, num_predictions=140, bribery_cost_usd=bribery_cost_usd),
        ValidatorProfile("agent-novice",   brier_score=0.25, num_predictions=25,  bribery_cost_usd=bribery_cost_usd),
    ]


def scaled_validators(
    n: int,
    avg_brier: float = 0.15,
    avg_predictions: int = 150,
    bribery_cost_usd: float = 250.0,
) -> list[ValidatorProfile]:
    """Generate a homogeneous validator pool of size N for scaling analysis."""
    return [
        ValidatorProfile(
            agent_id=f"validator-{i:03d}",
            brier_score=avg_brier,
            num_predictions=avg_predictions,
            bribery_cost_usd=bribery_cost_usd,
        )
        for i in range(n)
    ]


def production_validators(
    n: int,
    bribery_cost_usd: float = 1000.0,
) -> list[ValidatorProfile]:
    """Simulate a production-grade pool with realistic Brier distribution.

    Tier distribution (informed by forecasting literature):
      - 20% high-accuracy (Brier ≤ 0.10)
      - 50% mid-tier    (Brier 0.10–0.20)
      - 30% low-tier    (Brier 0.20–0.30)
    """
    validators = []
    for i in range(n):
        frac = i / max(n - 1, 1)
        if frac < 0.20:
            brier = 0.08 + frac / 0.20 * 0.02       # 0.08–0.10
            preds = 300
        elif frac < 0.70:
            t = (frac - 0.20) / 0.50
            brier = 0.10 + t * 0.10                  # 0.10–0.20
            preds = 150
        else:
            t = (frac - 0.70) / 0.30
            brier = 0.20 + t * 0.10                  # 0.20–0.30
            preds = 60
        validators.append(ValidatorProfile(
            agent_id=f"validator-{i:03d}",
            brier_score=brier,
            num_predictions=preds,
            bribery_cost_usd=bribery_cost_usd,
        ))
    return validators


# ---------------------------------------------------------------------------
# Scaling analyses
# ---------------------------------------------------------------------------

def pool_size_scaling(
    pool_sizes: list[int],
    market_size_usd: float,
    bribery_cost_usd: float = 250.0,
    cost_per_sybil_usd: float = 5.0,
) -> list[ScalingPoint]:
    """Security parameter as a function of validator pool size."""
    results = []
    for n in pool_sizes:
        pool = scaled_validators(n, bribery_cost_usd=bribery_cost_usd)
        sp = security_parameter(pool, market_size_usd, cost_per_sybil_usd)
        results.append(ScalingPoint(
            variable="pool_size",
            value=n,
            min_attack_cost_usd=sp.min_attack_cost_usd,
            security_ratio=sp.security_ratio,
            is_secure=sp.is_economically_secure,
        ))
    return results


def market_size_scaling(
    market_sizes: list[float],
    pool_size: int = 10,
    bribery_cost_usd: float = 250.0,
    cost_per_sybil_usd: float = 5.0,
) -> list[ScalingPoint]:
    """Security parameter as a function of market size at fixed pool size."""
    pool = scaled_validators(pool_size, bribery_cost_usd=bribery_cost_usd)
    sp_base = security_parameter(pool, market_sizes[0], cost_per_sybil_usd)
    base_attack_cost = sp_base.min_attack_cost_usd

    results = []
    for m in market_sizes:
        ratio = base_attack_cost / m
        results.append(ScalingPoint(
            variable="market_size_usd",
            value=m,
            min_attack_cost_usd=base_attack_cost,
            security_ratio=ratio,
            is_secure=ratio > 1.0,
        ))
    return results


def minimum_viable_pool_for_market(
    market_size_usd: float,
    bribery_cost_usd: float = 250.0,
    cost_per_sybil_usd: float = 5.0,
    max_pool: int = 500,
) -> int:
    """Binary-search the smallest pool size where security_ratio > 1.0."""
    lo, hi = 1, max_pool
    # Check if even max_pool is insufficient
    pool = scaled_validators(hi, bribery_cost_usd=bribery_cost_usd)
    sp = security_parameter(pool, market_size_usd, cost_per_sybil_usd)
    if not sp.is_economically_secure:
        return -1   # Market too large for this bribery cost at max pool

    while lo < hi:
        mid = (lo + hi) // 2
        pool = scaled_validators(mid, bribery_cost_usd=bribery_cost_usd)
        sp = security_parameter(pool, market_size_usd, cost_per_sybil_usd)
        if sp.is_economically_secure:
            hi = mid
        else:
            lo = mid + 1
    return lo


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def _fmt_usd(amount: float) -> str:
    if amount >= 1_000_000:
        return f"${amount/1_000_000:.2f}M"
    if amount >= 1_000:
        return f"${amount/1_000:.1f}K"
    return f"${amount:.2f}"


def format_security_report(
    sp: SecurityParameter,
    verbose: bool = True,
) -> str:
    lines = []
    sep = "─" * 70
    lines.append("Swarm Oracle — Economic Security Model")
    lines.append(sep)
    lines.append(f"Market size:       {_fmt_usd(sp.market_size_usd)}")
    lines.append(f"Validator pool:    {sp.validator_pool_size} agents")
    lines.append(sep)

    # Sybil path
    s = sp.sybil_attack
    lines.append(f"Sybil attack ({s.target_flip}):")
    lines.append(f"  Sybils required:  {s.num_sybils_required:,}")
    lines.append(f"  Cost per Sybil:   {_fmt_usd(s.cost_per_sybil_usd)}")
    lines.append(f"  Total Sybil cost: {_fmt_usd(s.total_cost_usd)}")

    # Bribery path
    b = sp.bribery_attack
    lines.append(f"Bribery attack ({b.target_flip}):")
    lines.append(f"  Agents to flip:   {b.num_agents_flipped}")
    lines.append(f"  Targets:          {', '.join(b.agents_flipped) or 'none'}")
    lines.append(f"  Total bribe cost: {_fmt_usd(b.total_cost_usd)}")

    # Summary
    lines.append(sep)
    lines.append(f"Cheapest vector:   {sp.cheapest_vector.upper()}")
    lines.append(f"Min attack cost:   {_fmt_usd(sp.min_attack_cost_usd)}")
    lines.append(f"Security ratio:    {sp.security_ratio:.3f}×")
    status = "✓ SECURE" if sp.is_economically_secure else "✗ INSECURE"
    lines.append(f"Status:            {status}")
    lines.append(sep)
    return "\n".join(lines)


def format_scaling_table(
    points: list[ScalingPoint],
    variable_label: str,
    fixed_label: str,
) -> str:
    lines = []
    col_w = 18
    header = f"{'Variable':>{col_w}} | {'Min Attack Cost':>18} | {'Security Ratio':>14} | Status"
    lines.append(f"  {fixed_label}")
    lines.append(f"  {'─' * (len(header) + 2)}")
    lines.append(f"  {header}")
    lines.append(f"  {'─' * (len(header) + 2)}")
    for p in points:
        var_str = (
            _fmt_usd(p.value)
            if "usd" in p.variable
            else f"{int(p.value)} validators"
        )
        status = "✓ secure" if p.is_secure else "✗ insecure"
        lines.append(
            f"  {var_str:>{col_w}} | {_fmt_usd(p.min_attack_cost_usd):>18} | "
            f"{p.security_ratio:>13.3f}× | {status}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# JSON serialisation
# ---------------------------------------------------------------------------

def _sp_to_dict(sp: SecurityParameter) -> dict:
    """Serialise a SecurityParameter to a JSON-compatible dict."""
    d = asdict(sp)
    # Convert inf/nan to string sentinels for JSON safety
    def scrub(obj):
        if isinstance(obj, float):
            if math.isinf(obj):
                return "inf"
            if math.isnan(obj):
                return "nan"
            return obj
        if isinstance(obj, dict):
            return {k: scrub(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [scrub(i) for i in obj]
        return obj
    return scrub(d)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="economic_model",
        description="Swarm Oracle economic security analysis",
    )
    parser.add_argument(
        "--market-size", type=float, default=10_000.0,
        help="Market size in USD (default 10,000)"
    )
    parser.add_argument(
        "--validators", type=int, default=3,
        help="Validator pool size (default 3 — demo pool)"
    )
    parser.add_argument(
        "--bribery-cost", type=float, default=250.0,
        help="Per-agent bribery cost in USD (default 250)"
    )
    parser.add_argument(
        "--sybil-cost", type=float, default=5.0,
        help="Per-Sybil registration cost in USD (default 5)"
    )
    parser.add_argument(
        "--pool-scaling", action="store_true",
        help="Print security vs pool size table"
    )
    parser.add_argument(
        "--market-scaling", action="store_true",
        help="Print security vs market size table"
    )
    parser.add_argument(
        "--mvp", action="store_true",
        help="Print minimum viable pool size for various market sizes"
    )
    parser.add_argument(
        "--json", type=str, default=None, metavar="PATH",
        help="Write full JSON output to this path"
    )
    args = parser.parse_args(argv)

    # Base analysis
    if args.validators == 3:
        pool = demo_validators(bribery_cost_usd=args.bribery_cost)
    else:
        pool = production_validators(args.validators, bribery_cost_usd=args.bribery_cost)

    sp = security_parameter(pool, args.market_size, args.sybil_cost)
    print(format_security_report(sp))

    if args.pool_scaling:
        sizes = [1, 2, 3, 5, 10, 20, 50, 100, 200]
        points = pool_size_scaling(sizes, args.market_size, args.bribery_cost, args.sybil_cost)
        print()
        print(format_scaling_table(
            points,
            "pool_size",
            f"Pool-size scaling | market={_fmt_usd(args.market_size)}, "
            f"bribery_cost/agent={_fmt_usd(args.bribery_cost)}, "
            f"sybil_cost={_fmt_usd(args.sybil_cost)}"
        ))

    if args.market_scaling:
        markets = [1_000, 5_000, 10_000, 50_000, 100_000, 500_000, 1_000_000]
        points = market_size_scaling(markets, args.validators, args.bribery_cost, args.sybil_cost)
        print()
        print(format_scaling_table(
            points,
            "market_size_usd",
            f"Market-size scaling | pool={args.validators} validators, "
            f"bribery_cost/agent={_fmt_usd(args.bribery_cost)}, "
            f"sybil_cost={_fmt_usd(args.sybil_cost)}"
        ))

    if args.mvp:
        print()
        print("Minimum viable pool size for market security")
        print(f"  (bribery_cost/agent={_fmt_usd(args.bribery_cost)}, sybil_cost={_fmt_usd(args.sybil_cost)})")
        print(f"  {'Market Size':>15} | {'Min Pool':>10} | {'Min Bribery Cost':>18}")
        print(f"  {'─' * 50}")
        for m in [1_000, 5_000, 10_000, 50_000, 100_000, 500_000, 1_000_000]:
            mvp = minimum_viable_pool_for_market(m, args.bribery_cost, args.sybil_cost)
            if mvp == -1:
                pool_str = ">500 (infeasible)"
                cost_str = "N/A"
            else:
                min_pool = scaled_validators(mvp, bribery_cost_usd=args.bribery_cost)
                sp_min = security_parameter(min_pool, m, args.sybil_cost)
                cost_str = _fmt_usd(sp_min.min_attack_cost_usd)
                pool_str = str(mvp)
            print(f"  {_fmt_usd(m):>15} | {pool_str:>10} | {cost_str:>18}")

    if args.json:
        out_path = Path(args.json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "security_parameter": _sp_to_dict(sp),
        }
        if args.pool_scaling:
            data["pool_scaling"] = [asdict(p) for p in points]   # type: ignore[possibly-undefined]
        out_path.write_text(json.dumps(data, indent=2))
        print(f"\nJSON written to {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
