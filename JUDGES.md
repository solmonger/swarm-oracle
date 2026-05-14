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

A 12-case curated benchmark, balanced 6 YES / 6 NO, with each agent
designed to be wrong on a different subset. Reproduce with `make benchmark`.

| Method        | Accuracy | Brier &darr; | Log loss &darr; |
|---------------|---------:|-------------:|----------------:|
| **swarm**     | **91.7%**| **0.0859**   | **0.2950**      |
| agent-oracle  | 83.3%    | 0.0870       | 0.2803          |
| average       | 91.7%    | 0.1184       | 0.3854          |
| agent-reliable| 83.3%    | 0.1112       | 0.3447          |
| majority vote | 83.3%    | 0.1667       | 3.4539          |
| agent-novice  | 66.7%    | 0.2340       | 0.6612          |

The swarm protocol wins on accuracy **and** Brier. Majority-vote's
log-loss collapses to 3.45 because hard 0/1 votes get murdered by
log-loss whenever they're wrong &mdash; exactly the brittleness
calibration weighting is designed to replace.

---

## Verify it yourself

```bash
git clone https://github.com/solmonger/swarm-oracle.git
cd swarm-oracle

# 1. Run the demo (no LLM needed, deterministic, ~3 seconds)
python swarm_verify.py --demo "Did BTC close above 100K on May 5, 2026?"

# 2. Run every Python test (~30 seconds)
make test                  # 154 tests, all passing

# 3. Run the Foundry tests (~5 seconds, needs `forge`)
make test-solidity         # 55 tests, all passing

# 4. Verify Python = Solidity bit-for-bit
make test-parity           # 14 cross-engine parity tests

# 5. Reproduce the benchmark above
make benchmark             # prints the comparison table
make benchmark-html        # writes benchmark.html with charts
```

No API keys. No paid services. Demo mode runs with zero network calls.

---

## Watch it

| Asset                | URL                                                |
|----------------------|----------------------------------------------------|
| 90-second demo       | https://youtu.be/Dy1h0Hcr4HQ                       |
| Live landing page    | https://solmonger.github.io/swarm-oracle/          |
| Interactive demo     | [demo.html](demo.html) (open locally or via Pages) |
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
2. Clone the repo. `make demo` &mdash; watch three parallel agents reason on
   the same question. `make benchmark` &mdash; watch the swarm beat its own
   member agents on Brier.
3. [`contracts/src/SwarmConsensus.sol`](contracts/src/SwarmConsensus.sol)
   and [`contracts/src/RewardDistribution.sol`](contracts/src/RewardDistribution.sol).
4. [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) for the Base Sepolia
   deployment recipe.
5. [`docs/SUBMISSION_DEVNETWORK.md`](docs/SUBMISSION_DEVNETWORK.md) for
   the full submission narrative.

---

## What's novel

1. **Calibration as the trust primitive.** Most oracles use stake, identity,
   or hand-rolled committees. Swarm Oracle uses Brier-score history &mdash; an
   objective, recomputable, on-chain-verifiable signal of past accuracy.
2. **Python &harr; Solidity parity is mechanically tested.** Not a code
   review, not a hope &mdash; 14 cross-engine fixtures asserting bit-for-bit
   equality. The math doesn't drift between layers.
3. **Disputes are first-class.** When weighted variance crosses a
   threshold, the protocol emits `DISPUTE` rather than forcing YES/NO.
   This is what well-calibrated humans do when they don't know; the
   protocol does the same.
4. **Self-improving without re-deploy.** Every resolution updates Brier
   scores, which updates weights, which improves future predictions.
   No governance vote, no migration.
5. **Local-first.** Works against any OpenAI-compatible endpoint &mdash;
   `llama.cpp`, Ollama, vLLM. Demo mode requires zero network. The
   competitive cost story (and the security story) starts from there.

---

## Tech stack

- **Python 3.10+** &mdash; engine, agents, FastAPI server, benchmarking
- **Solidity 0.8.24 + Foundry** &mdash; on-chain mirror
- **Base Sepolia** &mdash; target L2 (low gas, EVM-equivalent)
- **WAD fixed-point math** &mdash; no external math libs, no `sqrt`
- **OpenAI-compatible LLM API** &mdash; works with llama.cpp, Ollama, vLLM, OpenAI, Anthropic
- **No paid services required.** No API keys in the demo path.

---

## License & contact

MIT licensed. See [LICENSE](LICENSE) for terms.

Project page: https://devpost.com/software/swarm-oracle
GitHub: https://github.com/solmonger/swarm-oracle
