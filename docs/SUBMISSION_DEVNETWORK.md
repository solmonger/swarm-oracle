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
- **Formal adversarial analysis** — 90 pinned tests covering collusion (Symmetric Collusion Lemma), adaptive attacker, and bribery vector with the N×B>M economic security formula

## Technical Details

**Python engine (zero external dependencies):**
- `consensus.py` — weighted linear opinion pool with YES/NO/DISPUTE thresholds
- `weights.py` — Brier → calibration weight formula with confidence ramp for new agents
- `verifier.py` — ThreadPoolExecutor parallel orchestration
- `agent.py` — SwarmAgent with pluggable research strategies
- `evidence.py` — CoinGecko API, DuckDuckGo search, knowledge-only strategies
- `api.py` — FastAPI service with `/resolve` and `/compare` endpoints
- `adversarial.py` — multi-vector adversarial simulation (collusion, adaptive, bribery)
- `sybil.py` — Sybil resistance analysis with variance gate
- `economic_model.py` — security parameter ρ and N×B>M production formula

**Solidity contracts (Base Sepolia):**
- `CalibrationRegistry.sol` — per-agent Brier storage + WAD weight computation
- `SwarmConsensus.sol` — on-chain vote aggregation reading registry weights
- `RewardDistribution.sol` — ETH reward pools with calibration-weighted splits
- `AgentIdentity.sol` — soulbound ERC-721 reputation tokens

**Testing (797 total):**
- 742 Python tests (consensus math, weights, agents, API endpoints, on-chain bridge, demo mode, adversarial, Sybil, economic security, benchmark, landing page, repo norms, Jupyter notebook, submission readiness gate)
- 55 Foundry tests for all 4 contracts
- 14 cross-verification parity tests (Python ↔ Solidity math match)
- 90 adversarial simulation tests (collusion × 7, adaptive × 5, bribery × 8, composition × 5, invariants × 3, formatters × 7, demos × 5)
- 50 economic security model tests (weight parity × 11, Sybil cost × 6, bribery cost × 6, security parameter × 7, scaling × 6, MVP × 4, CLI × 6, public surface × 2)
- 83 Sybil resistance tests (registration × 9, single-weight × 7, multi-Sybil × 11, variance gate × 8, boundary × 5, invariants × 7, demo × 6, stats × 5)

**CI pipeline (6-job GitHub Actions):**
- `python-tests` — full suite on Python 3.11 and 3.12
- `benchmark` — 50-case run + swarm Brier < ALL baselines assertion
- `adversarial` — adversarial + economic model tests + CLI smoke tests
- `solidity-tests` — Foundry with gas report + EIP-170 contract size check
- `repo-health` — required files present + doc staleness check
- `ci-pass` — summary gate: all jobs must pass

**Infrastructure:**
- Local-first: runs on consumer hardware with any OpenAI-compatible LLM server
- No API keys, no rate limits, no cost per query
- Docker Compose deployment

## Results / Metrics

- **Benchmark:** swarm Brier 0.0724 vs 0.1029 for best single agent (100% accuracy, 50-case, seed=42)
- **Security:** Symmetric Collusion Lemma proven + tested at k = 1, 2, 5, 20; bribery/Sybil crossover at B* ≈ avg_weight × 17 × C_reg
- **Economic model:** N×B>M formula (validator count × per-agent bribery cost > market size); minimum viable pool tables for market sizes $1K–$1M
- 3-agent consensus completes in ~3.3s on Apple M4 Max with local inference
- On-chain math matches Python engine bit-for-bit across all test cases

## Security Analysis

**docs/threat-model.md** presents a formal multi-vector adversarial analysis:
- **Collusion:** Symmetric Collusion Lemma — an attacker controlling k agents of equal weight needs W_sybil ≥ W_honest × 5.667 to flip a decision. Proven and pinned by tests at k ∈ {1, 2, 5, 20}.
- **Adaptive attacker:** concentrated vote ≡ single-Sybil bound — budget-splitting never improves attack efficiency.
- **Bribery:** greedy highest-weight-first algorithm is optimal; in a 3-agent swarm bribery costs $500 vs $1,360 for Sybil (2.7× cheaper).
- **Production implication:** the crossover to Sybil-dominates-bribery occurs at ≥10 high-weight validators with $2k/agent bribery cost — documented as the transition from hackathon → production deployment.

**docs/ECONOMIC_MODEL.md** introduces the security parameter ρ = min(C_sybil, C_bribery) / M and the production invariant N×B>M.

## Competitive Positioning

**docs/competitive-comparison.md** benchmarks Swarm Oracle against UMA, Augur v2, Reality.eth, Chainlink, and Pyth across 9 dimensions (trust model, settlement time, per-resolution cost, attack-cost basis, LLM-native, etc.). Key differentiator: Swarm Oracle is the only protocol where trust is derived from verifiable prediction accuracy rather than stake, governance, or identity.

## Demo

- **CLI:** `python swarm_verify.py --demo "Did BTC close above $100K on May 5?"` (no server needed)
- **Interactive dashboard:** `demo.html` — browser-based visualization with preset questions
- **Jupyter notebook:** `notebooks/swarm_oracle_demo.ipynb` — 7-part interactive walkthrough; browser-renderable on GitHub, no LLM required
- **API:** `POST /resolve` and `POST /compare` endpoints
- **Video:** https://youtu.be/Dy1h0Hcr4HQ
- **Live landing page:** https://solmonger.github.io/swarm-oracle/

## Tech Stack

Python 3.10+ (stdlib only), Solidity 0.8.28, Foundry, FastAPI (optional), Base Sepolia L2, GitHub Actions

## Team

Eshaan Mathakari — solo developer

## Repository

https://github.com/SolMonger/swarm-oracle

## What's Novel

1. **Brier-weighted consensus** — first open-source implementation of calibration-weighted multi-agent aggregation for on-chain oracle
2. **On-chain parity** — Python and Solidity produce identical results, verified by automated parity tests
3. **Self-improving architecture** — resolution data feeds back into both weight updates and DPO fine-tuning
4. **Zero-dependency Python** — entire engine uses only stdlib, making it deployable anywhere
5. **Dispute detection** — weighted variance prevents false consensus when well-calibrated agents genuinely disagree
6. **Formal adversarial analysis** — first oracle project to prove Symmetric Collusion Lemma and derive a bribery/Sybil cost crossover, backed by 90 executable tests
7. **Economic security model** — quantitative framework for deployment sizing; N×B>M formula with 50 tests verifying against actual protocol constants
8. **Interactive Jupyter notebook** — 7-part walkthrough viewable in GitHub browser without installation; runs all claims against real data
