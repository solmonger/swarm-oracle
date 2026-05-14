# Swarm Oracle Security Model

This document analyzes the economic security of calibration-weighted consensus
against a Sybil attacker who tries to flip a resolution by injecting fake
agents into the protocol. The reference implementation is
[`swarm_oracle/sybil.py`](../swarm_oracle/sybil.py); every result here is
reproduced by [`tests/test_sybil.py`](../tests/test_sybil.py) (83 tests) and
can be regenerated locally with `make sybil-demo`.

## TL;DR

1. **Cheap Sybils are bounded by base-weight count.** Each fresh agent
   contributes at most `BASE_WEIGHT = 1.0`. Flipping a YES decision in the
   canonical demo scenario costs ≥ **272 base-weight Sybils** — and that's
   *with* the variance gate doing extra work (the naive mean-only bound is
   78; the variance gate roughly 3.5× the cost).
2. **High-weight Sybils require real calibration.** A constant-vote
   attacker's expected Brier score is bounded below by the Bernoulli
   variance `r·(1−r)` of the resolution. At a balanced base rate (`r=0.5`),
   that floor is `0.25` — capping the attacker's per-Sybil weight at
   `3.984`, well below the oracle-tier weight `~9.99`.
3. **To match an oracle-tier agent, a Sybil must actually be calibrated.**
   No constant-vote strategy reaches oracle weight at any base rate near
   `0.5`. A Sybil with Brier `0.09` (genuinely accurate) needs 91+
   predictions in the registry — at which point it isn't acting like a
   Sybil any more.
4. **Disputes are intentionally cheap to inject** (1 base-weight Sybil
   suffices in the demo scenario), but disputes don't flip resolutions —
   they trigger fallback. A high dispute rate is observable and signals an
   attack rather than concealing one.

## Notation

We model an honest swarm of `H` agents producing votes `p_h ∈ [0, 1]` with
calibration weights `w_h ∈ ℝ≥0`. An attacker injects `S` Sybils each voting
the same `p_s ∈ [0, 1]` with weight `w_s`. The protocol aggregates:

```
p(new) = (Σ_h w_h · p_h  +  S · w_s · p_s) / (Σ_h w_h  +  S · w_s)
```

We write `A = Σ_h w_h · p_h` and `W = Σ_h w_h`, so the honest swarm
produces `p_honest = A/W`. The aggregate Sybil weight is `W_s = S · w_s`.

Decision thresholds (from `consensus.py`):

| Constant | Default | Meaning |
| --- | --- | --- |
| `DEFAULT_YES_THRESHOLD` | `0.85` | `p ≥ 0.85` → YES |
| `DEFAULT_NO_THRESHOLD` | `0.15` | `p ≤ 0.15` → NO |
| `DEFAULT_VARIANCE_THRESHOLD` | `0.20` | weight-aware variance above this → DISPUTE |

## 1. The Mean-Crossing Lower Bound

To force `p(new) ≥ 0.85`, the attacker must satisfy

```
A + W_s · p_s ≥ 0.85 · (W + W_s)
```

Rearranging, with the optimal attacker vote `p_s = 1`:

```
W_s ≥ (0.85 · W − A) / (1 − 0.85)
    = (0.85 · W − A) / 0.15
```

A symmetric expression governs NO flips with `p_s = 0`:

```
W_s ≥ (A − 0.15 · W) / 0.15
```

**Reading the demo numbers.** The canonical demo (three agents from
`weights.mock_brier_history`) gives `W ≈ 16.42` and `A ≈ 2.28`. The
closed-form lower bound for a YES flip is:

```
W_s ≥ (0.85 · 16.42 − 2.28) / 0.15  ≈  77.83
```

→ ~**78 base-weight Sybils** if the attacker stops at the mean threshold.

## 2. The Variance Gate

The lower bound above is *necessary* but not *sufficient*. Even after the
mean crosses the YES threshold, the consensus engine checks the
*weight-aware variance*

```
Var = Σ_i (w_i/W_total) · (p_i − p_new)²
```

against `DEFAULT_VARIANCE_THRESHOLD = 0.20`. At the mean-crossing minimum,
honest agents are clustered far from the attacker's `p_s = 1`, the Sybil
mass is itself far from the new mean, and the resulting variance is high —
typically high enough to trigger `DISPUTE` rather than `YES`.

The attacker therefore has to *over-attack*: pile on enough Sybils that the
honest votes become a negligible fraction of total weight, at which point
variance collapses back below threshold (because the attacker has
homogenized the distribution).

**In the demo scenario:** the true cost rises from the closed-form 78 to
**272 base-weight Sybils** — a `3.5×` multiplier just from the variance
gate. The variance threshold is doing real work as a second line of
defense, even though it's framed in `consensus.py` primarily as a "high
disagreement → escalate" rule.

Reproducible by `python -m scripts.sybil_demo --target YES` (see
[scripts/sybil_demo.py](../scripts/sybil_demo.py)).

## 3. The Calibration Ceiling

If raw count is the attacker's only currency, 272 Sybils is cheap (gas
aside). The protocol's deeper defense is the calibration weighting itself:
each Sybil's weight is

```
w_s = (1 / (brier_s + EPSILON)) · min(1, n / CONFIDENCE_THRESHOLD)
```

where `brier_s` is the Sybil's running-average Brier score in the registry
and `n` is its prediction count. A Sybil cannot conjure a high weight from
nothing — it has to *earn* one by predicting accurately.

### 3.1 The constant-vote strategy

Suppose a Sybil picks one probability `p` and votes it on every question.
Outcomes resolve YES with base rate `r`. The Sybil's expected per-prediction
Brier is

```
E[Brier] = (1−r) · p²  +  r · (1−p)²
```

Differentiating with respect to `p` and setting to zero:

```
2 · p · (1−r) − 2 · (1−p) · r = 0
=>  p = r
```

So the **best constant-vote strategy is `p = r`**, giving the minimum
expected Brier

```
E[Brier]_min = r · (1 − r)
```

This is exactly the variance of a Bernoulli random variable — the
irreducible loss of guessing the mean. From this, the **maximum attainable
weight for a constant-vote Sybil** is

```
w_s_max = 1 / (r · (1 − r) + EPSILON)
```

(at `n ≥ CONFIDENCE_THRESHOLD`).

| Base rate `r` | min E[Brier] | max Sybil weight |
| --- | --- | --- |
| 0.10 | 0.0900 | 10.989 |
| 0.30 | 0.2100 | 4.739 |
| 0.50 | 0.2500 | 3.984 |
| 0.70 | 0.2100 | 4.739 |
| 0.90 | 0.0900 | 10.989 |

Oracle-tier agents in `mock_brier_history` have Brier `0.10` and weight
`~9.99`. For balanced base rates `r ∈ [0.3, 0.7]`, **no constant-vote Sybil
can match oracle weight at any prediction count.** For heavily skewed base
rates (`r → 0` or `r → 1`), a Sybil that always votes the modal outcome can
reach a high weight — but only because *the outcome itself is nearly
deterministic*, in which case the protocol is correctly rewarding a
"clock-twice-a-day" agent that happens to know the answer.

### 3.2 The time cost

Even matching a balanced-base-rate ceiling weight of `3.984` requires
`MIN_PREDICTIONS = 20` predictions before the protocol assigns *any* weight
above `BASE_WEIGHT = 1.0`. To reach the full ceiling, the Sybil needs
`CONFIDENCE_THRESHOLD = 100` predictions (more than `100 · (brier + EPS)`
exactly).

A stealth Sybil network must therefore operate for **at least 20 question
cycles** before launching its attack. That's an observable horizon: the
network has 20+ cycles to detect coordinated behavior, correlated voting
patterns, or shared infrastructure.

### 3.3 The actually-good-Sybil case

What if the attacker really *is* good at predicting? A Sybil with Brier
`0.09` reaches oracle weight in `91` predictions
(`sybil_break_even_predictions(9.99, 0.09)` → `90.0990...`).

At that point the "Sybil" is, by definition, an accurate predictor — the
protocol's weighting is correctly amplifying its voice. **A Sybil that's
indistinguishable from an honest agent gets to vote like an honest agent.**
That's the protocol working as designed, not a vulnerability.

## 4. The Dispute Surface

`DISPUTE` is intentionally easy to trigger. In the demo scenario, **a
single base-weight Sybil** suffices to push the consensus into the
uncertainty band and trigger fallback resolution. This is a *feature*:

1. Disputes don't flip resolutions; they escalate them. The protocol's
   answer becomes "we can't tell", which is honest under uncertainty.
2. A high dispute rate is publicly observable. An attacker that converts
   90% of resolutions into disputes is paying a 90%-visibility cost.
3. Sustained dispute spam isn't a flip; it's a denial-of-service. That's
   handled by per-agent rate limits and gas costs on the
   `SwarmConsensus.sol` contract.

The economic security goal is to make *adversarial flips* hard, not to
make *adversarial confusion* hard. The two threats have different
mitigations.

## 5. The Combined Picture

For an attacker to flip the canonical demo scenario YES, they must either:

| Path | Cost | Visibility |
| --- | --- | --- |
| Spam base-weight Sybils | 272 agents (gas: ~272 × `registerAgent`) | Public on-chain registrations |
| Build constant-vote calibration first | 91+ predictions per Sybil, then ceiling at `w ≈ 3.98` (needs 69+ such Sybils) | 20+ cycle delay; correlated voting patterns |
| Become an actually-calibrated predictor | Match oracle Brier 0.10 in registry | Indistinguishable from honest agent — and weighted accordingly |

Each row gets progressively more expensive and more observable. The
combined defense is not any single mechanism but the *compositional*
hardness of meeting all of them at once.

## 6. Reproducing the Numbers

Every number in this document comes from `swarm_oracle.sybil` and is
re-derived under continuous test:

```bash
# All 83 Sybil tests pass.
python -m pytest tests/test_sybil.py -v

# Run the canonical demo and print a publication-grade attack report.
make sybil-demo

# Explore alternative scenarios.
python -m scripts.sybil_demo --target YES --base-rate 0.5
python -m scripts.sybil_demo --target NO --base-rate 0.5
python -m scripts.sybil_demo --target DISPUTE --base-rate 0.5
```

For the curated headline numbers (272 cost, 3.984 ceiling, etc.), see the
`make benchmark` output once the benchmark bundle is synced (commands in
`docs/SUBMISSION_DEVNETWORK.md`).

## 7. Limitations and Future Work

This analysis treats the registry's calibration scores as ground truth.
In practice, three additional concerns are out of scope here and tracked
in the roadmap:

1. **Adaptive attackers.** A Sybil that votes the *true* base rate when
   uncertain but flips to a target value on the question it cares about can
   pay a smaller Brier penalty per attack-question. A token-bucket on
   per-agent "flip events" would harden this; we have not implemented it.
2. **Collusion across registered identities.** The current analysis
   assumes one attacker controls all Sybils; we model their aggregate
   weight `W_s`. Collusion between separately-registered "honest" agents
   is no worse than this case but is harder to detect.
3. **Outcome oracles.** The Brier score is computed against resolved
   outcomes from a settlement oracle. If the settlement oracle itself is
   compromised, the calibration registry inherits the compromise. This is
   a meta-level concern shared by every protocol that resolves market
   outcomes.

Each is a known open problem; this document quantifies the protocol's
defenses *against the threat model it was designed for*. The math is
honest about what it covers.
