# For judges

Welcome. This page is a two-minute orientation written specifically for
hackathon judges. If you have time to read one thing, read [The 30-second
pitch](#the-30-second-pitch). If you have time to run one thing, run
[Verify it yourself](#verify-it-yourself).

---

## The 30-second pitch

**Problem.** Oracles today trust capital, not accuracy. A whale with stake
gets to decide what's true. UMA, Chainlink, and similar designs all share
that pattern, and it breaks under adversarial conditions.

**Solution.** Swarm Oracle weights truth by *historical calibration*. Each
participating AI agent submits a probability for a binary question. Each
agent's vote is weighted by the inverse of its historical Brier score
(plus a confidence ramp). Better-calibrated agents get more influence.
Worse-calibrated agents get less. The math is two lines; you can read it
in [`swarm_oracle/weights.py`](swarm_oracle/weights.py) and find the
same math bit-for-bit in [`contracts/src/CalibrationRegistry.sol`](contracts/src/CalibrationRegistry.sol).

**Why it matters.** Every resolution becomes training data. Calibration
scores update. Future predictions sharpen. The protocol is
self-improving without a re-deploy.

---

## Headline result

A 50-case deterministic benchmark (seed=42), balanced YES/NO, with each agent
designed to fail on different subsets so the swarm detects disagreement. Reproduce
with `make benchmark`.

| Method          | Accuracy   | Brier ↓  | Notes                          |
|-----------------|:----------:|:--------:|--------------------------------|
| **swarm**       | **100%**   | **0.0724** | DISPUTE = correct abstention |
| majority vote   | 92.0%      | 0.0785   |                                |
| average         | 98.0%      | 0.0935   |                                |
| agent-oracle    | 84.0%      | 0.1029   | Best single agent              |
| agent-reliable  | 80.0%      | 0.1332   |                                |
| agent-novice    | 68.0%      | 0.2009   |                                |

The swarm beats **every** single agent on Brier score. The variance gate
correctly identifies cases where agents genuinely disagree and emits
`DISPUTE` rather than forcing a wrong answer — that is accuracy, not failure.

---

## Verify it yourself

```bash
git clone https://github.com/solmonger/swarm-oracle.git
cd swarm-oracle

# 1. Run the demo (no LLM needed, deterministic, ~3 seconds)
python swarm_verify.py --demo "Did BTC close above 100K on May 5, 2026?"

# 2. Run every Python test (~30 seconds)
make test                  # 742 tests, all passing

# 3. Run the Foundry tests (~5 seconds, needs `forge`)
make test-solidity         # 55 tests, all passing

# 4. Verify Python = Solidity bit-for-bit
make test-parity           # 14 cross-engine parity tests

# 5. Reproduce the benchmark above
make benchmark             # 50-case, seed=42 — swarm Brier 0.0724

# 6. Run the adversarial simulation
make adversarial-compare   # shows bribery vs Sybil cost comparison

# 7. Run the economic security model
make economic-model-mvp    # shows minimum viable pool by market size

# 8. Open the interactive notebook (no LLM needed)
jupyter notebook notebooks/swarm_oracle_demo.ipynb
```

No API keys. No paid services. Demo mode runs with zero network calls.
The Jupyter notebook can be viewed directly on GitHub (browser-renderable).

---

## Watch it

| Asset                | URL                                                |
|----------------------|----------------------------------------------------|
| 90-second demo       | https://youtu.be/Dy1h0Hcr4HQ                       |
| Live landing page    | https://solmonger.github.io/swarm-oracle/          |
| Interactive demo     | [demo.html](demo.html) (open locally or via Pages) |
| Jupyter notebook     | [notebooks/swarm_oracle_demo.ipynb](notebooks/swarm_oracle_demo.ipynb) |
| Devpost submission   | https://devpost.com/software/swarm-oracle          |
| Benchmark report     | [benchmark.html](benchmark.html)                   |

---

## What to look at if you have...

### 5 minutes
1. The 90-second video.
2. This page.
3. The `make benchmark` table.

### 15 minutes
1. Everything in the 5-minute path.
2. [`swarm_oracle/weights.py`](swarm_oracle/weights.py) (the weight formula, 60 lines).
3. [`swarm_oracle/consensus.py`](swarm_oracle/consensus.py) (the consensus + dispute logic, 200 lines).
4. [`contracts/src/CalibrationRegistry.sol`](contracts/src/CalibrationRegistry.sol) (the Solidity mirror, 180 lines).
5. `make test-parity` to see Python = Solidity proven on 14 cases.

### 45 minutes
1. The 15-minute path.
2. Clone the repo. `make demo` — watch three parallel agents reason on
   the same question. `make benchmark` — watch the swarm beat its own
   member agents on Brier.
3. [`contracts/src/SwarmConsensus.sol`](contracts/src/SwarmConsensus.sol)
   and [`contracts/src/RewardDistribution.sol`](contracts/src/RewardDistribution.sol).
4. [`docs/threat-model.md`](docs/threat-model.md) — formal multi-vector adversarial
   analysis (collusion, adaptive attacker, bribery) with 90 pinned tests.
   Key insight: bribery is cheaper than Sybil by 2.7× in a 3-agent swarm.
5. [`docs/ECONOMIC_MODEL.md`](docs/ECONOMIC_MODEL.md) — security parameter ρ,
   the N×B>M production formula, and minimum viable pool tables.
6. [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) for the Base Sepolia
   deployment recipe.
7. [`docs/SUBMISSION_DEVNETWORK.md`](docs/SUBMISSION_DEVNETWORK.md) for
   the full submission narrative.

---

## What's novel

1. **Calibration as the trust primitive.** Most oracles use stake, identity,
   or hand-rolled committees. Swarm Oracle uses Brier-score history — an
   objective, recomputable, on-chain-verifiable signal of past accuracy.
2. **Python ↔ Solidity parity is mechanically tested.** Not a code
   review, not a hope — 14 cross-engine fixtures asserting bit-for-bit
   equality. The math doesn't drift between layers.
3. **Disputes are first-class.** When weighted variance crosses a
   threshold, the protocol emits `DISPUTE` rather than forcing YES/NO.
   This is what well-calibrated humans do when they don't know; the
   protocol does the same.
4. **Self-improving without re-deploy.** Every resolution updates Brier
   scores, which updates weights, which improves future predictions.
   No governance vote, no migration.
5. **Local-first.** Works against any OpenAI-compatible endpoint —
   `llama.cpp`, Ollama, vLLM. Demo mode requires zero network. The
   competitive cost story (and the security story) starts from there.
6. **Formal adversarial analysis with 90 pinned tests.** Collusion
   (Symmetric Collusion Lemma at k = 1, 2, 5, 20), adaptive attacker
   (concentrated ≡ single-Sybil bound), and bribery vector — each
   proved mathematically and verified by an executable test. The
   bribery-dominates-Sybil finding at small scale is a genuine
   insight: documented, honest, and shows the production path.
7. **Economic security model with N×B>M formula.** Security parameter
   ρ = min(C_sybil, C_bribery) / M quantifies how much a market can
   pay out and remain economically secure. 50 tests verify the math
   against actual protocol constants. Phase 1/2/3 scaling tables give
   a concrete production roadmap.
8. **Interactive Jupyter notebook — browser-renderable.** 7-part
   walkthrough of the full protocol: calibration weights, consensus
   formation, benchmark results, adversarial analysis, economic security,
   on-chain architecture, full test suite. No LLM required for any cell.
   GitHub renders it natively in the browser.

---

## Tech stack

- **Python 3.10+** — engine, agents, FastAPI server, benchmarking
- **Solidity 0.8.24 + Foundry** — on-chain mirror
- **Base Sepolia** — target L2 (low gas, EVM-equivalent)
- **WAD fixed-point math** — no external math libs, no `sqrt`
- **OpenAI-compatible LLM API** — works with llama.cpp, Ollama, vLLM, OpenAI, Anthropic
- **No paid services required.** No API keys in the demo path.

---

## CI / Quality signals

The repository ships a 6-job CI pipeline (`.github/workflows/ci.yml`):

| Job | What it verifies |
|-----|-----------------|
| `python-tests` | Full 742-test suite on Python 3.11 and 3.12 |
| `benchmark` | 50-case benchmark + asserts swarm Brier < ALL single agents |
| `adversarial` | 90 adversarial + 50 economic model tests + CLI smoke tests |
| `solidity-tests` | Foundry with gas report + EIP-170 24 KB contract size check |
| `repo-health` | Required files present + doc staleness check |
| `ci-pass` | Summary gate: all jobs must pass |

The CI badge at the top of README.md is real — click it to see the last run.

---

## License & contact

MIT licensed. See [LICENSE](LICENSE) for terms.

Project page: https://devpost.com/software/swarm-oracle
GitHub: https://github.com/solmonger/swarm-oracle
