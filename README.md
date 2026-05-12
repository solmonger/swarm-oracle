# Swarm Oracle

**Calibration-weighted multi-agent prediction oracle.**

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
git clone https://github.com/eshaan-mathakari/swarm-oracle.git
cd swarm-oracle

# Install in editable mode (zero runtime deps; tests require pytest)
pip install -e .

# --- Demo mode (no LLM, no network needed) ---
python3 -m swarm_oracle.cli --demo "Will BTC hit 100k?"

# Or via the convenience entry-point
python3 swarm_verify.py --demo "Will BTC hit 100k?"

# Three-question recorded demo
bash record-demo.sh   # writes demo-recording.txt

# --- Live mode (requires an OpenAI-compatible LLM server) ---
export LLM_API_URL="http://localhost:8080/v1/chat/completions"
python3 swarm_verify.py "Will ETH close above $3,000 on June 1, 2026?"

# JSON output (machine-readable)
python3 swarm_verify.py --demo --json "Will BTC be above $100K tomorrow?"

# With on-chain submission (requires web3.py + deployed contracts)
python3 swarm_verify.py --on-chain \
  --registry-addr 0x42987D1753e6290B68273Ff8310E7f8248290890 \
  --consensus-addr 0xF0F393D1bFA815537F9FcfC6e6520e0379A1071a \
  "Did ETH close above $3,500 on May 10?"
```

### Demo output (verified 2026-05-12)

`python3 -m swarm_oracle.cli --demo "Will BTC hit 100k?"` returns three
deterministic agent votes (BTC ≈ $81K), a weighted consensus probability of
~0.07, variance ~0.012, and decision `NO` — finished in <2s. The `--json`
flag emits the same data as a single JSON object.

### LLM Server

Swarm Oracle works with any OpenAI-compatible chat completions endpoint. Set `LLM_API_URL` to point at your server:

- [llama.cpp](https://github.com/ggerganov/llama.cpp) — `./server -m model.gguf --port 8080`
- [Ollama](https://ollama.ai) — `ollama serve` (default: `http://localhost:11434/v1/chat/completions`)
- [vLLM](https://github.com/vllm-project/vllm) — `python -m vllm.entrypoints.openai.api_server`

No API keys needed. No paid services required.

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
├── tests/                       # Python test suite (133 tests, 3 skipped)
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
# Python tests — 133 passing, 3 intentionally skipped (~8s)
python3 -m pytest tests/ -v

# Solidity tests — 57 passing (requires Foundry)
cd contracts && forge test -vv

# Cross-verification: Python↔Solidity math parity
python3 -m pytest tests/test_solidity_math_parity.py -v
```

### Test counts (last verified 2026-05-12)

| Suite                      | Passing | Skipped | Notes                                       |
|----------------------------|---------|---------|---------------------------------------------|
| Solidity (`forge test`)    | 57      | 0       | 4 test files, full coverage of all contracts |
| Python (`pytest tests/`)   | 133     | 3       | Skipped tests are intentional placeholders   |
| `forge build` warnings     | 0       | —       | Zero lint warnings                           |

## Contracts

Deployed on **Base Sepolia** testnet (chain ID 84532).

### Deployed Contracts

| Contract | Address |
|----------|---------|
| CalibrationRegistry | [`0x42987D1753e6290B68273Ff8310E7f8248290890`](https://sepolia.basescan.org/address/0x42987D1753e6290B68273Ff8310E7f8248290890) |
| SwarmConsensus | [`0xF0F393D1bFA815537F9FcfC6e6520e0379A1071a`](https://sepolia.basescan.org/address/0xF0F393D1bFA815537F9FcfC6e6520e0379A1071a) |
| RewardDistribution | [`0xa9B3bB31dbe15DD26031Fe899284F267308D625B`](https://sepolia.basescan.org/address/0xa9B3bB31dbe15DD26031Fe899284F267308D625B) |
| AgentIdentity | [`0x5bD8b36214d002cB250Be1c9a82022875331b947`](https://sepolia.basescan.org/address/0x5bD8b36214d002cB250Be1c9a82022875331b947) |

Deployer: [`0xF822f19C0FEc804f002e9087523677195a3C96cE`](https://sepolia.basescan.org/address/0xF822f19C0FEc804f002e9087523677195a3C96cE)

### Contract Details

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

## Hackathon

Built for the [DevNetwork AI+ML Hackathon](https://devnetwork.com) (May 2026) and [Kite AI Global Hackathon](https://kiteai.com).

**The narrative:** "We didn't just build an oracle. We built a system that gets more accurate every time it's used."

## License

MIT — see [LICENSE](LICENSE).
