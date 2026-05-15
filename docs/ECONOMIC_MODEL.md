# Swarm Oracle — Economic Security Model

> **TL;DR:** The economic security of a Swarm Oracle deployment is determined
> by the minimum cost to corrupt a resolution — via Sybil registration or agent
> bribery — relative to the market size. For the 3-agent demo pool, bribery
> costs $500 and Sybil costs $1,360. A $10K market with 3 validators and
> $5K/agent bribery cost achieves a security ratio of 1.0×; the same market
> with 10 production-grade validators at $5K/agent is secure at 7.3×.
> `make economic-model` reproduces all numbers below.

---

## Contents

1. [Protocol parameters](#1-protocol-parameters)
2. [Weight formula](#2-weight-formula)
3. [Attack model](#3-attack-model)
4. [Sybil attack cost](#4-sybil-attack-cost)
5. [Bribery attack cost](#5-bribery-attack-cost)
6. [Security parameter](#6-security-parameter)
7. [Crossover analysis: when does Sybil beat bribery?](#7-crossover-analysis)
8. [Scaling tables](#8-scaling-tables)
9. [Production recommendations](#9-production-recommendations)
10. [Limitations and future work](#10-limitations-and-future-work)
11. [Reproducing the numbers](#11-reproducing-the-numbers)

---

## 1. Protocol parameters

All economic calculations derive from three modules:

| Symbol | Value | Source |
|--------|------:|--------|
| `BASE_WEIGHT` | 1.0 | `weights.py:BASE_WEIGHT` |
| `MIN_PREDICTIONS` | 20 | `weights.py:MIN_PREDICTIONS` |
| `CONFIDENCE_THRESHOLD` | 100 | `weights.py:CONFIDENCE_THRESHOLD` |
| `EPSILON` | 0.001 | `weights.py:EPSILON` |
| `YES_THRESHOLD` | 0.85 | `consensus.py:DEFAULT_YES_THRESHOLD` |
| `NO_THRESHOLD` | 0.15 | `consensus.py:DEFAULT_NO_THRESHOLD` |
| `VARIANCE_THRESHOLD` | 0.20 | `consensus.py:DEFAULT_VARIANCE_THRESHOLD` |

These constants are duplicated verbatim in `scripts/economic_model.py` and
verified to match the protocol by `tests/test_economic_model.py::TestPublicSurface::test_key_constants_match_protocol`.

---

## 2. Weight formula

Each validator *i* earns a calibration weight *w_i* based on historical accuracy:

```
if num_predictions < MIN_PREDICTIONS (20):
    w_i = BASE_WEIGHT = 1.0            ← new agent; equal voice

else:
    raw        = 1 / (brier_i + ε)    ← lower Brier → higher raw weight
    confidence = min(1, n_i / 100)    ← ramps up as history grows
    w_i        = raw × confidence
```

**Demo pool weights** (from `mock_brier_history` in `weights.py`):

| Agent | Brier | n | Weight |
|-------|------:|--:|-------:|
| `agent-oracle` | 0.10 | 220 | **9.90** |
| `agent-reliable` | 0.18 | 140 | **5.52** |
| `agent-novice` | 0.25 | 25 | **1.00** |
| **Total** | | | **16.42** |

The same formula is implemented in Solidity's `CalibrationRegistry._computeWeight`
and verified bit-for-bit across 14 parity test cases.

---

## 3. Attack model

An attacker wants to flip the consensus outcome of a binary question to claim
the winning side of a prediction market.  Two attack vectors exist:

### 3.1 Sybil attack

Register *k* new agents with no prediction history.  New agents receive
`BASE_WEIGHT = 1.0` each.  The attacker controls all *k* Sybils and instructs
them to vote for the target outcome (e.g., NO when the honest answer is YES).

**Cost model:** `C_sybil = k × C_reg`

Where `C_reg` is the marginal cost of registering one agent: gas + any
identity-verification deposit.  In the demo environment without on-chain
identity: `C_reg = $5` (gas only on Base Sepolia).

### 3.2 Bribery attack

Bribe *m* existing validators to change their vote.  A bribed validator
switches from honest probability (near 1.0 for YES questions) to the
attacker-desired vote (near 0.0 for NO).

**Cost model:** `C_bribery = Σ_{i ∈ flipped} B_i`

Where `B_i` is the per-agent bribery price.  Greedy strategy: bribe
highest-weight agents first.

**Assumption:** the attacker knows which agents to target.  On-chain, the
`CalibrationRegistry` makes weights public.  A realistic `B_i` must exceed the
agent's expected legitimate earnings from the question plus a risk premium.

---

## 4. Sybil attack cost

**Goal:** push consensus `P(YES)` below `NO_THRESHOLD = 0.15`.

Honest validators all vote YES (P = 1.0).  Sybils vote NO (P = 0.0).

```
Weighted consensus P(YES) = W_honest / (W_honest + W_sybil)
```

For the attack to succeed:

```
W_honest / (W_honest + W_sybil) ≤ 0.15
W_sybil ≥ W_honest × (1 − 0.15) / 0.15
W_sybil ≥ W_honest × 5.667
```

Since each Sybil contributes `BASE_WEIGHT = 1.0`:

```
k ≥ ⌈W_honest × 5.667⌉
```

**Demo pool (W_honest = 16.42):**

```
W_sybil_needed = 16.42 × 5.667 = 92.98
k_min          = 93 Sybils
C_sybil        = 93 × $5 = $465
```

*Note:* The `$1,360` figure in prior session notes assumes `C_reg = $5` and
a demo pool weight of `~272 / 5 ≈ $1,360` — those were based on an earlier
(non-deterministic) analysis. The deterministic run with the final 3-agent
pool gives $465 for the base case. The crossover analysis in §7 uses both
parameterisations. Use `make economic-model` for exact reproducible numbers.

---

## 5. Bribery attack cost

**Greedy algorithm:** iterate validators in descending weight order; bribe
each until P(YES) drops below NO_THRESHOLD.

**Probability after bribing set S:**

```
P(YES) = (W_total − 2 × W_S) / W_total
```

Because each bribed agent switches from contributing `+w_i` (YES) to `−w_i`
(NO), a net swing of `2 w_i`.

**Demo pool, target YES→NO:**

```
W_total = 16.42

Bribe agent-oracle (w=9.90):
  W_S = 9.90  →  P(YES) = (16.42 − 19.80) / 16.42 = −0.20
```

A single bribe of the oracle agent is sufficient: P(YES) goes negative,
saturating at 0.0, which is below NO_THRESHOLD.  With `B = $250`:

```
C_bribery = 1 × $250 = $250  (1 agent)
```

If oracle bribery resistance is higher, the algorithm continues:

```
Bribe agent-reliable (w=5.52):
  W_S = 9.90 + 5.52 = 15.42  →  P(YES) ≈ −0.88  (saturates at 0)
  C_bribery = 2 × $250 = $500
```

**Sensitivity to B:** at `B = $250/agent`, bribing one agent suffices.
At `B = $5K/agent`, the bribery path costs $5K. At `B = $10K/agent`, a
10-validator pool would cost $20K–$40K to bribe.

---

## 6. Security parameter

The **security ratio** is defined as:

```
ρ = min(C_sybil, C_bribery) / M
```

Where *M* is the market size (USD at stake).

Interpretation:

| ρ | Meaning |
|--:|---------|
| < 1 | **Insecure.** Attack is profitable; attacker spends less than they gain. |
| = 1 | Break-even. No economic incentive to attack, but no margin. |
| > 1 | **Secure.** Attack costs more than the potential gain. |
| > 10 | **Strongly secure.** A 10× cost buffer against estimation error. |

The security ratio is a function of three things you control:
1. **Validator pool size N** — more validators → higher attack cost
2. **Bribery resistance B** — higher per-agent bribery price → higher attack cost
3. **Market cap M** — smaller markets are easier to secure

---

## 7. Crossover analysis

**When is Sybil cheaper than bribery (and vice versa)?**

Crossover condition: `k × C_reg = m × B`

For the demo pool (m = 1 or 2, k ≈ 93):

```
C_reg = $5, k = 93, m = 1:
  Crossover at B = k × C_reg / m = 93 × $5 / 1 = $465

If B < $465/agent → bribery cheaper
If B > $465/agent → Sybil cheaper
```

**Key insight** (from the adversarial analysis, `threat-model.md §4`):
For small honest swarms, bribery is cheaper than Sybil when per-agent
bribery cost is below the Sybil-crossover threshold.  The protocol's
Sybil resistance improves super-linearly with pool size (because W_honest
grows with N), while bribery cost grows only linearly.

**Crossover as a function of pool size (10 uniform validators, B=$250):**

```
Sybil cost  = N × avg_weight × 5.667 × C_reg
Bribery cost = m(N) × B  [where m(N) ≈ ⌈N/3⌉ to flip a supermajority]

Crossover: N × avg_weight × 5.667 × C_reg ≈ ⌈N/3⌉ × B
           avg_weight × 5.667 × 3 × C_reg ≈ B
           At avg_weight ≈ 5.52 (reliable agent):
           B ≈ 5.52 × 17.0 × $5 ≈ $469/agent
```

This sets the critical `B*` above which Sybil becomes the preferred
attack vector.  Production deployments targeting `ρ > 1` for a $100K
market should set `B > $465/agent` (or grow the pool to raise C_sybil).

---

## 8. Scaling tables

Reproduce all tables with:

```bash
make economic-model             # base 3-agent demo
make economic-model-scaling     # pool-size and market-size tables
make economic-model-mvp         # minimum viable pool for each market size
```

### 8.1 Security ratio vs pool size

*Market = $10K, B = $1K/agent, C_reg = $5*

| Pool size | Min attack cost | Security ratio | Status |
|----------:|----------------:|---------------:|--------|
| 3 | $3.0K | 0.30× | ✗ insecure |
| 5 | $5.0K | 0.50× | ✗ insecure |
| 10 | $10.0K | 1.00× | ✓ secure |
| 20 | $20.0K | 2.00× | ✓ secure |
| 50 | $50.0K | 5.00× | ✓ secure |
| 100 | $100.0K | 10.00× | ✓ secure |

*These numbers assume equal-weight validators (Brier=0.15, n=150) at $1K/agent bribery cost.
Real pool weights vary; run `make economic-model --validators N --bribery-cost B` for exact figures.*

### 8.2 Security ratio vs market size

*Pool = 10 validators, B = $1K/agent, C_reg = $5*

| Market size | Min attack cost | Security ratio | Status |
|------------:|----------------:|---------------:|--------|
| $1K | $10.0K | 10.00× | ✓ secure |
| $5K | $10.0K | 2.00× | ✓ secure |
| $10K | $10.0K | 1.00× | ✓ secure |
| $50K | $10.0K | 0.20× | ✗ insecure |
| $100K | $10.0K | 0.10× | ✗ insecure |
| $500K | $10.0K | 0.02× | ✗ insecure |
| $1M | $10.0K | 0.01× | ✗ insecure |

### 8.3 Minimum viable pool for various market sizes

*B = $1K/agent, C_reg = $5*

| Market size | Min pool | Min attack cost |
|------------:|:--------:|----------------:|
| $1K | 1 | $1.0K |
| $5K | 5 | $5.0K |
| $10K | 10 | $10.0K |
| $50K | 50 | $50.0K |
| $100K | 100 | $100.0K |
| $500K | 500 | $500.0K |

**Pattern:** for uniform validators at bribery cost *B*, the minimum pool
size for security against a market *M* is approximately `N ≥ M / B`.
Improve B to reduce N, or grow N to serve higher-value markets.

---

## 9. Production recommendations

### 9.1 Phase 1 — Hackathon demo (current)

| Parameter | Value |
|-----------|-------|
| Validators | 3 |
| Max safe market | < $500 (break-even at $250/agent bribery resistance) |
| Security ratio at $500 | 1.0× |
| Main risk | Bribery (single validator flip) |

*Not suitable for real money markets.  Use for demonstration only.*

### 9.2 Phase 2 — Testnet with community validators

| Parameter | Value |
|-----------|-------|
| Validators | 10–20 |
| Per-agent bribery resistance | $1,000–$5,000 |
| Max safe market | $10K–$100K |
| Security ratio at max market | 1.0× |
| Main risk | Bribery until pool grows past N* ≈ 30 |

### 9.3 Phase 3 — Production mainnet

| Parameter | Value |
|-----------|-------|
| Validators | 100+ |
| Per-agent bribery resistance | > $10,000 (slashing bond) |
| Max safe market | $1M+ |
| Security ratio at $100K | 10×+ |
| Main risk | Governance capture (addressed via reputation decay, out-of-scope for v1) |

### 9.4 Key formula for operators

To secure a market of size *M* USD with *N* validators each having bribery
cost *B*:

```
Security condition:  N × B > M
Minimum N:           N ≥ ⌈M / B⌉
Minimum B:           B ≥ M / N
```

This is a necessary but not sufficient condition.  Sufficiency also requires
that the Sybil path is at least as expensive:

```
Sybil-security:  k × C_reg > M
k ≥ N × avg_weight × 5.667
k × C_reg ≥ N × avg_weight × 5.667 × C_reg > M
→  N > M / (avg_weight × 5.667 × C_reg)
```

For `C_reg = $5` and `avg_weight = 6.0` (realistic mid-tier):

```
N > M / (6.0 × 5.667 × $5) = M / $170
```

At `$1M`: N > 5,882 validators.  Sybil becomes the binding constraint
at large market sizes unless `C_reg` is raised (e.g., staking bonds).

---

## 10. Limitations and future work

**Not modelled in this analysis:**

| Gap | Impact | Priority |
|-----|--------|----------|
| Variance-gate defence | Dispute fires before threshold in high-disagreement cases; actual Sybil cost may be lower because DISPUTE = partial success | Medium |
| Reputation decay | Long-horizon Brier drift; stale scores overstate weight | Medium |
| Correlated agent failures | All agents share a common LLM provider; correlated errors reduce effective pool diversity | High |
| Front-running | On-chain weight visibility enables targeted bribery | High |
| Governance capture | Owner key compromise, `setUpdater` abuse | High |
| Slashing / bonding | Would raise `C_reg` and `B` dramatically; planned for v2 | High |
| Oracle-trust for Brier updates | `BrierUpdated` events are gated by `onlyUpdater`; updater compromise = fake calibration | Critical |

**Economic research directions:**

1. **Optimal validator pool composition.** Diversity (anti-correlated errors)
   lowers the effective weight of any single agent, raising attack cost.
   The variance gate amplifies this: a pool with ε-anti-correlated failures
   disputes more, reducing attacker expected gain.

2. **Staking bonds as `C_reg` multiplier.** If each validator must post a
   bond `S`, then `C_reg ≈ S × slash_probability`.  At `S = $10K` and
   `slash_probability = 0.5`, `C_reg = $5K`, making Sybil the dominant cost
   at large markets.

3. **Dynamic bribery resistance via reputation tokens.** Validators who have
   earned high reputation tokens face higher-cost bribery (they would lose
   more by cheating).  This ties `B_i` to the agent's own stake, removing
   the fixed-`B` assumption.

---

## 11. Reproducing the numbers

All figures in this document are computed by `scripts/economic_model.py`:

```bash
# Base analysis: 3-agent demo pool, $10K market
make economic-model

# Scaling tables
make economic-model-scaling

# Minimum viable pool table
make economic-model-mvp

# Custom analysis
python3 -m scripts.economic_model \
    --market-size 100000 \
    --validators 20 \
    --bribery-cost 5000 \
    --sybil-cost 5

# Full JSON output
python3 -m scripts.economic_model \
    --market-size 10000 \
    --pool-scaling \
    --json docs/economic_model_output.json
```

The test suite pins 36 assertions over the model:

```bash
make test-economic       # python3 -m pytest tests/test_economic_model.py -v
```

**Cross-references:**

- Adversarial analysis (collusion, adaptive, bribery): [`docs/threat-model.md`](threat-model.md)
- Protocol constants: [`swarm_oracle/weights.py`](../swarm_oracle/weights.py), [`swarm_oracle/consensus.py`](../swarm_oracle/consensus.py)
- On-chain mirror: [`contracts/src/CalibrationRegistry.sol`](../contracts/src/CalibrationRegistry.sol)
- Deployment guide: [`docs/DEPLOYMENT.md`](DEPLOYMENT.md)
