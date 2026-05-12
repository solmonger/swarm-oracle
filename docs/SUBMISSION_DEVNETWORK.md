# DevNetwork AI+ML Hackathon — Submission Draft

**Project:** Swarm Oracle  
**Category:** AI/ML  
**Deadline:** ~May 18, 2026 (submit early)

---

## Project Title

Swarm Oracle: Calibration-Weighted Multi-Agent Prediction Consensus

## One-Line Description

A self-improving prediction oracle that weights multiple AI agents by their historical accuracy (Brier scores) and verifies consensus math on-chain.

## Problem Statement

Single-model AI predictions are unreliable because you can't measure how much to trust the answer. Models vary in accuracy across domains, and there's no mechanism to learn from past performance. Prediction markets solve trust with money, but that excludes most AI agents and most questions.

## Solution

Swarm Oracle runs 3+ AI agents in parallel on any binary question. Each agent researches independently using different strategies (API lookup, web search, knowledge). Their probability estimates are combined using calibration weights derived from Brier scores — a strictly proper scoring rule that rewards honest, accurate forecasts.

Key innovations:
- **Calibration weighting** — agents earn influence through accuracy, not stake
- **Dispute detection** — weighted variance identifies genuine disagreement instead of forcing false consensus
- **On-chain verification** — Solidity contracts on Base Sepolia reproduce the Python math in 18-decimal fixed-point, enabling trustless verification
- **Self-improving loop** — every resolved question updates Brier scores and generates DPO training data for agent fine-tuning

## Technical Details

**Python engine (zero external dependencies):**
- `consensus.py` — weighted linear opinion pool with YES/NO/DISPUTE thresholds
- `weights.py` — Brier → calibration weight formula with confidence ramp for new agents
- `verifier.py` — ThreadPoolExecutor parallel orchestration
- `agent.py` — SwarmAgent with pluggable research strategies
- `evidence.py` — CoinGecko API, DuckDuckGo search, knowledge-only strategies
- `api.py` — FastAPI service with `/resolve` and `/compare` endpoints

**Solidity contracts (Base Sepolia):**
- `CalibrationRegistry.sol` — per-agent Brier storage + WAD weight computation
- `SwarmConsensus.sol` — on-chain vote aggregation reading registry weights
- `RewardDistribution.sol` — ETH reward pools with calibration-weighted splits
- `AgentIdentity.sol` — soulbound ERC-721 reputation tokens

**Testing:**
- 133 Python tests (consensus math, weights, agents, API, on-chain bridge, demo mode)
- 55 Foundry tests across all 4 contracts
- 14 cross-verification parity tests (Python ↔ Solidity math match)

**Infrastructure:**
- Local-first: runs on consumer hardware with any OpenAI-compatible LLM server
- No API keys, no rate limits, no cost per query
- GitHub Actions CI across Python 3.10/3.11/3.12 + Foundry

## Results / Metrics

- 3-agent consensus completes in ~3.3s on Apple M4 Max with local inference
- 29 scored forecasts with mean Brier 0.157
- 13/29 model wins vs. market closing price
- Calibration weighting demonstrably dampens low-confidence agents while amplifying accurate ones
- On-chain math matches Python engine bit-for-bit across all test cases

## Demo

- **CLI:** `python swarm_verify.py --demo "Did BTC close above $100K on May 5?"` (no server needed)
- **Interactive dashboard:** `demo.html` — browser-based visualization with preset questions
- **API:** `POST /resolve` and `POST /compare` endpoints
- **Video:** [link to demo video]

## Tech Stack

Python 3.10+ (stdlib only), Solidity 0.8.28, Foundry, FastAPI (optional), Base Sepolia L2, GitHub Actions

## Team

Eshaan Mathakari — solo developer

## Repository

https://github.com/solmonger/swarm-oracle

## What's Novel

1. **Brier-weighted consensus** — first open-source implementation of calibration-weighted multi-agent aggregation
2. **On-chain parity** — Python and Solidity produce identical results, verified by automated parity tests
3. **Self-improving architecture** — resolution data feeds back into both weight updates and DPO fine-tuning
4. **Zero-dependency Python** — entire engine uses only stdlib, making it deployable anywhere
5. **Dispute detection** — weighted variance prevents false consensus when well-calibrated agents genuinely disagree
