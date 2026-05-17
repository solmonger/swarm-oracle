# Swarm Oracle

**Calibration-weighted multi-agent prediction oracle.**

[![CI](https://github.com/solmonger/swarm-oracle/actions/workflows/ci.yml/badge.svg)](https://github.com/solmonger/swarm-oracle/actions/workflows/ci.yml)

> **Live demo:** [solmonger.github.io/swarm-oracle](https://solmonger.github.io/swarm-oracle/) &middot;
> **Video:** [90-second walkthrough](https://youtu.be/Dy1h0Hcr4HQ) &middot;
> **Hackathon judges:** start with [`JUDGES.md`](JUDGES.md)

Swarm Oracle runs multiple AI agents in parallel on the same yes/no question, then combines their probability estimates using calibration weights derived from each agent's historical [Brier score](https://en.wikipedia.org/wiki/Brier_score). Better-calibrated agents get more influence. The result is a consensus probability that outperforms any single agent or naive majority vote.

On-chain contracts on Base Sepolia mirror the Python math, so anyone can verify the weights and consensus independently.

```
$ python swarm_verify.py "Did BTC close above 100K on May 5, 2026?"
========================================================================
  SWARM ORACLE  |  Calibration-Weighted Consensus
========================================================================
Question : Did BTC close above 100K on May 5, 2026?
Agents   : 3
Elapsed  : 3.30s

Individual votes:
  agent-oracle     | strategy=api         | P(YES)=0.030 | conf=0.90 | weight= 10.00 ( 60.1%) ████████████········
  agent-reliable   | strategy=web_search  | P(YES)=0.050 | conf=0.80 | weight=  5.56 ( 33.5%) ███████·············
  agent-novice     | strategy=knowledge   | P(YES)=0.500 | conf=0.00 | weight=  1.07 (  6.4%) █···················

Consensus:
  Weighted P(YES) = 0.0303
  Variance        = 0.0143
  Decision        = NO
========================================================================
```

## How It Works

1. **Question in** — any binary (yes/no) prediction question
2. **Parallel agent research** — each agent uses a different strategy (API lookup, web search, knowledge-only) and reasons independently
3. **Calibration weighting** — weights are computed from historical Brier scores: `weight = 1 / (brier + ε)`, scaled by a confidence ramp for agents with fewer predictions
4. **Weighted consensus** — linear opinion pool produces a single probability
5. **Dispute detection** — if weighted variance exceeds a threshold, the result is flagged as DISPUTE rather than forced to YES/NO
6. **On-chain verification** — CalibrationRegistry.sol and SwarmConsensus.sol replicate the math in fixed-point Solidity (WAD, 18 decimals)

## Quick Start

```bash
# Clone
git clone https://github.com/SolMonger/swarm-oracle.git
cd swarm-oracle

# Run (requires an OpenAI-compatible LLM server)
export LLM_API_URL="http://localhost:8080/v1/chat/completions"
python swarm_verify.py "Will ETH close above $3,000 on June 1, 2026?"

# JSON output
python swarm_verify.py --json "Will BTC be above $100K tomorrow?"

# With on-chain submission (requires web3.py + deployed contracts)
python swarm_verify.py --on-chain \
  --registry-addr 0x... --consensus-addr 0x... \
  "Did ETH close above $3,500 on May 10?"
```

### LLM Server

Swarm Oracle works with any OpenAI-compatible chat completions endpoint. Set `LLM_API_URL` to point at your server:

- [llama.cpp](https://github.com/ggerganov/llama.cpp) — `./server -m model.gguf --port 8080`
- [Ollama](https://ollama.ai) — `ollama serve` (default: `http://localhost:11434/v1/chat/completions`)
- [vLLM](https://github.com/vllm-project/vllm) — `python -m vllm.entrypoints.openai.api_server`

No API keys needed. No paid services required.

### Docker (One Command)

```bash
# API server with interactive docs
docker compose up                         # → http://localhost:8000/docs

# Quick demo (no LLM needed)
docker compose run oracle demo

# Run the full test suite
docker compose run oracle test

# Or without compose:
docker build -t swarm-oracle .
docker run -p 8000:8000 swarm-oracle
```

### Testing

```bash
make test               # 742 Python tests (all passing)
make test-solidity      # 55 Foundry tests
make test-integration   # end-to-end pipeline tests
```

## Live Demo & Submission Assets

| What                  | URL                                                           |
|-----------------------|---------------------------------------------------------------|
| GitHub Pages          | https://solmonger.github.io/swarm-oracle/                      |
| Interactive demo      | [demo.html](demo.html) (open locally or via Pages)             |
| Benchmark report      | [benchmark.html](benchmark.html)                               |
| 90-second video       | https://youtu.be/Dy1h0Hcr4HQ                                   |
| DevPost project page  | https://devpost.com/software/swarm-oracle                      |
| Judges' quickstart    | [JUDGES.md](JUDGES.md)                                         |

The landing page (`index.html`) is hand-rolled, single-file, zero-CDN. Every
visual token mirrors `demo.html`, so the site looks like the protocol from any
entry point. Pushes to `main` auto-publish via `.github/workflows/pages.yml`.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    swarm_verify.py                       │
│                   (CLI entry point)                      │
└─────────────┬───────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────┐
│                  verifier.py                             │
│          ThreadPoolExecutor orchestrator                 │
│        (runs N agents in parallel)                       │
└───┬──────────┬──────────────────┬───────────────────────┘
    │          │                  │
    ▼          ▼                  ▼
┌────────┐ ┌────────────┐ ┌───────────┐
│ agent  │ │   agent    │ │   agent   │
│ oracle │ │ reliable   │ │  novice   │
│ (API)  │ │(web search)│ │(knowledge)│
└───┬────┘ └─────┬──────┘ └─────┬─────┘
    │            │              │
    └──────┬─────┘──────────────┘
           ▼
┌─────────────────────────────────────────────────────────┐
│                consensus.py                              │
│     Weighted linear opinion pool + dispute detection     │
│     weights from weights.py (Brier → calibration)        │
└─────────────────────────┬───────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│              on_chain.py + bridge.py                     │
│     Python ↔ Solidity submission & parity check          │
└─────────────────────────┬───────────────────────────────┘
                          │
          ┌───────────────┼───────────────┐
          ▼                               ▼
┌──────────────────┐            ┌──────────────────┐
│ CalibrationReg.  │            │ SwarmConsensus    │
│     .sol         │◄───────────│     .sol          │
│ (Brier storage   │  reads     │ (vote aggregation │
│  + weight calc)  │  weights   │  + resolution)    │
└────────┬─────────┘            └────────┬─────────┘
         │                               │
         ▼                               ▼
┌──────────────────┐            ┌──────────────────┐
│ AgentIdentity    │            │ RewardDistrib.    │
│     .sol         │            │     .sol          │
│ (soulbound NFT   │            │ (ETH rewards,     │
│  + live profile) │            │  pull-payment)    │
└──────────────────┘            └──────────────────┘
         Base Sepolia L2
```

## Project Structure

```
swarm-oracle/
├── swarm_verify.py              # CLI entry point
├── swarm_oracle/                # Python package (zero external deps)
│   ├── agent.py                 # SwarmAgent class + default 3-agent fleet
│   ├── cli.py                   # CLI wiring + pretty-printer
│   ├── consensus.py             # Weighted aggregation + dispute detection
│   ├── evidence.py              # Research strategies (CoinGecko, DuckDuckGo)
│   ├── api.py                   # FastAPI service (POST /resolve, /compare)
│   ├── on_chain.py              # Python→contract bridge integration
│   ├── verifier.py              # Parallel orchestrator
│   └── weights.py               # Brier → calibration weight formula
├── contracts/                   # Foundry Solidity contracts
│   ├── src/
│   │   ├── CalibrationRegistry.sol   # On-chain Brier storage + weight computation
│   │   ├── SwarmConsensus.sol        # Vote aggregation + resolution events
│   │   ├── RewardDistribution.sol    # ETH reward pools + accuracy-weighted payout
│   │   └── AgentIdentity.sol         # Soulbound ERC-721 agent reputation tokens
│   ├── test/
│   │   ├── CalibrationRegistry.t.sol # Foundry tests — registry
│   │   ├── SwarmConsensus.t.sol      # Foundry tests — consensus
│   │   ├── RewardDistribution.t.sol  # Foundry tests — rewards
│   │   └── AgentIdentity.t.sol       # Foundry tests — identity
│   └── script/
│       └── Deploy.s.sol              # Full-suite deployment (all 4 contracts)
├── tests/                       # Python test suite (742 tests)
├── docs/
│   └── DEPLOYMENT.md            # Base Sepolia deployment guide
└── examples/
    └── demo.sh                  # Quick demo script
```

## Key Design Decisions

**Off-chain aggregation, on-chain verification.** The heavy consensus math runs in Python. Solidity contracts store agent records, compute weights, and verify submitted results — but don't recompute the full aggregation. This keeps gas costs low while maintaining full transparency.

**Brier scoring for trust.** Unlike systems that weight by stake or reputation tokens, Swarm Oracle uses [Brier scores](https://en.wikipedia.org/wiki/Brier_score) — a strictly proper scoring rule. Agents can't game their weight without actually being more accurate.

**Weighted variance for disputes.** Instead of forcing consensus, the system detects genuine disagreement via weighted variance. When well-calibrated agents disagree strongly, the result is DISPUTE — not a misleading average.

**Zero external Python dependencies.** The entire Python package uses only stdlib (`json`, `math`, `urllib`, `concurrent.futures`, `dataclasses`, etc.). The LLM server is an external process, not a library dependency.

**Local-first inference.** Designed to run on consumer hardware with local LLM servers. No API keys, no rate limits, no cost per query.

## API Server

Swarm Oracle includes a FastAPI service for programmatic access and demo dashboards.

```bash
# Install API dependencies
pip install 'swarm-oracle[api]'

# Start the server
uvicorn swarm_oracle.api:app --host 0.0.0.0 --port 8000

# Or with auto-reload for development
python -m swarm_oracle.api
```

### Endpoints

**`POST /resolve`** — Run the swarm on a binary question:

```bash
curl -X POST http://localhost:8000/resolve \
  -H "Content-Type: application/json" \
  -d '{"question": "Did BTC close above $100K on May 5, 2026?"}'
```

Returns consensus probability, per-agent votes with evidence, calibration weights, and dispute detection.

**`POST /compare`** — Compare aggregation methods side-by-side:

```bash
curl -X POST http://localhost:8000/compare \
  -H "Content-Type: application/json" \
  -d '{"question": "Will ETH close above $3000 on June 1?"}'
```

Runs the same agents once, then shows how three methods interpret the votes: calibration-weighted swarm, equal-weight majority, and single best agent. This demonstrates the value of calibration weighting.

**`GET /health`** — Liveness check.

Interactive docs at `http://localhost:8000/docs` (Swagger UI) or `/redoc`.

## Running Tests

```bash
# Python tests (742 tests, ~33s)
python -m pytest tests/ -v

# Solidity tests (requires Foundry)
cd contracts && forge test -v

# Cross-verification: Python↔Solidity math parity
python -m pytest contracts/test/test_solidity_math_parity.py -v
```

## Contracts

Deployed on **Base Sepolia** testnet.

| Contract | Description |
|----------|-------------|
| `CalibrationRegistry.sol` | Stores per-agent Brier scores, computes calibration weights in 18-decimal fixed-point (WAD). Supports individual and batch seeding, incremental updates, and enumerable agent lists. |
| `SwarmConsensus.sol` | Reads weights from CalibrationRegistry, accepts vote submissions, computes weighted consensus probability, classifies YES/NO/DISPUTE, emits resolution events. Stores votes for on-chain audit. |
| `RewardDistribution.sol` | Distributes ETH reward pools to agents after consensus resolution. 70% split by calibration weight, 30% accuracy bonus for agents aligned with consensus. Pull-payment pattern. |
| `AgentIdentity.sol` | Soulbound ERC-721 tokens for agent reputation. Non-transferable — reputation is earned. `getAgentProfile()` aggregates identity + live calibration stats from the registry. |

### Contract Math

All values use WAD (1e18 = 1.0):

- **Weight formula:** `weight = WAD² / (brier + EPSILON)` where `EPSILON = 1e15` (0.001)
- **Confidence ramp:** agents with fewer than `MIN_PREDICTIONS` (20) get a flat base weight; between 20 and `CONFIDENCE_THRESHOLD` (100) predictions, weight scales linearly
- **Dispute detection:** uses `variance > threshold²` to avoid on-chain `sqrt()`
- **Decision thresholds:** YES ≥ 0.85, NO ≤ 0.15, else DISPUTE

## Results

- 3-agent swarm completes end-to-end in ~3.3s on Apple M4 Max with local inference
- 29 scored forecasts, mean Brier 0.157
- 13/29 model wins vs. market closing price
- Calibration weighting demonstrably dampens low-confidence novice agents while amplifying oracles
- Self-improving: every resolution becomes training data for future DPO fine-tuning

## Security Model

The protocol's economic security against Sybil attacks is documented and
quantified in [`docs/security-model.md`](docs/security-model.md). Headline
findings, derived from the canonical demo scenario:

- **Cheap Sybils are expensive.** Flipping a YES decision requires at
  least **272 base-weight Sybils** — the closed-form mean-crossing bound
  is 78, and the variance gate raises the true cost by `3.5×`.
- **High-weight Sybils require real calibration.** A constant-vote
  attacker's expected Brier is bounded below by `r·(1−r)`, capping
  per-Sybil weight at `~3.98` for balanced base rates — well below the
  oracle-tier weight of `~9.99`.
- **Disputes are intentionally cheap (1 Sybil), but disputes don't
  flip resolutions** — they trigger fallback. Sustained dispute spam is
  publicly observable and rate-limited on-chain.

Reproduce locally:

```bash
make sybil-demo                            # report for YES target
make sybil-demo-all                        # all three targets
python -m pytest tests/test_sybil.py -v   # 83 tests
```

The math is mirrored on-chain in `CalibrationRegistry.sol`; see
`tests/test_on_chain.py` for the Python↔Solidity parity tests.

## Threat Model (multi-vector adversarial analysis)

Beyond single-attacker Sybil, the protocol is analysed against
**collusion**, **adaptive attackers** (who see honest votes first), and
**economic bribery** in [`docs/threat-model.md`](docs/threat-model.md).
Numbers pinned by `tests/test_adversarial.py` (59 tests) and
`tests/test_adversarial_demo.py` (31 tests):

- **Symmetric Collusion Lemma.** *k* colluders with identical votes and
  summed weight *W* are operationally equivalent to one Sybil at weight
  *W* — splitting attack capital across more Sybil identities provides
  zero mean-stage benefit.
- **Adaptive attackers don't help.** A worst-case attacker who reads
  every honest vote before voting needs the same weight as one who
  guesses blindly — the protocol is information-resistant in that sense.
- **Bribery is the cheapest attack in the 3-agent regime.** $500 to
  flip 2 honest agents beats $1,360 to register 272 Sybils. The
  crossover (where Sybil becomes cheaper) sits around 10+
  high-weight agents at $2k/agent bribery cost — the production
  operating regime.

Reproduce:

```bash
make adversarial-demo                      # collusion + adaptive + bribery
make adversarial-compare                   # Sybil vs bribery USD comparison
python -m pytest tests/test_adversarial.py tests/test_adversarial_demo.py -v
```

## Economic Security Model

[`docs/ECONOMIC_MODEL.md`](docs/ECONOMIC_MODEL.md) introduces the security
parameter **ρ = min(C_sybil, C_bribery) / M** and the production invariant
**N × B > M** (validator count × per-agent bribery cost must exceed market
size). Verified by 50 tests against actual protocol constants.

Phase scaling (demo pool = oracle 9.90 weight + reliable 5.52 + novice 1.00):

| Pool size | Market size secure |
|-----------|-------------------|
| 3 agents  | < $1,500          |
| 10 agents | < $10,000         |
| 50 agents | < $100,000        |
| 200 agents| < $1,000,000      |

Reproduce:

```bash
make economic-model-mvp   # minimum viable pool by market tier
python -m pytest tests/test_economic_model.py -v  # 50 tests
```

## Competitive Positioning

[`docs/competitive-comparison.md`](docs/competitive-comparison.md)
positions Swarm Oracle against **UMA**, **Augur v2**, **Reality.eth +
Kleros**, **Chainlink Price Feeds**, and **Pyth Network**. Headline
takeaway: Swarm Oracle is the only oracle in that set that resolves
free-form questions in seconds (vs hours for UMA / Reality.eth) and the
only one that is **self-improving** via the DPO loop. Chainlink and Pyth
are complements (price-numeric), not competitors.

## Interactive Notebook

[`notebooks/swarm_oracle_demo.ipynb`](notebooks/swarm_oracle_demo.ipynb) —
7-part interactive Jupyter walkthrough. Browser-renderable on GitHub. No LLM
or server required.

| Part | What it demonstrates |
|------|----------------------|
| 1. Calibration Weights | `compute_weight` with bar charts |
| 2. Consensus Formation | YES / DISPUTE / NO scenarios |
| 3. Benchmark | 50-case results from benchmark.json |
| 4. Adversarial Analysis | Sybil + adaptive + bribery crossover |
| 5. Economic Security | ρ table + minimum viable pool |
| 6. On-Chain Architecture | contract preview + deploy commands |
| 7. Full Test Suite | `subprocess.run(pytest)` in-notebook |

```bash
jupyter notebook notebooks/swarm_oracle_demo.ipynb
```

## Testing

| Suite | Count | Command |
|-------|-------|---------|
| Full Python suite | 742 | `make test` |
| Adversarial (collusion / adaptive / bribery) | 90 | `make test-adversarial` |
| Sybil resistance | 83 | `python -m pytest tests/test_sybil.py` |
| Economic security model | 50 | `python -m pytest tests/test_economic_model.py` |
| Benchmark (deterministic 50-case) | 32 | `make test-benchmark` |
| Jupyter notebook structure | 34 | `python -m pytest tests/test_notebook.py` |
| Submission readiness gate | 55 | `python -m pytest tests/test_submission_readiness.py` |
| Python ↔ Solidity parity | 14 | `make test-parity` |
| Foundry (Solidity) | 55 | `make test-solidity` |
| **Total** | **797** | `make test && make test-solidity` |

CI verifies all 797 tests on every push (6-job pipeline, Python 3.11 + 3.12).

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the dev environment, test
expectations, and PR flow. Security issues: please follow the
coordinated-disclosure process in [`SECURITY.md`](SECURITY.md) rather than
filing a public issue.

## Hackathon

Built for the [DevNetwork AI+ML Hackathon](https://devnetwork.com) (May 2026) and [Kite AI Global Hackathon](https://kiteai.com).

**The narrative:** "We didn't just build an oracle. We built a system that gets more accurate every time it's used."

## License

MIT — see [LICENSE](LICENSE).
