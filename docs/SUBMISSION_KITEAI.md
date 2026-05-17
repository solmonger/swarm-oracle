# Kite AI Global Hackathon — Submission Draft

**Project:** Swarm Oracle  
**Category:** Agent Economy / Decentralized AI  
**Focus:** On-chain agent reputation and consensus verification

---

## Project Title

Swarm Oracle: On-Chain Calibration-Weighted Agent Consensus

## Elevator Pitch

Swarm Oracle creates a trustless agent economy where AI agents earn prediction influence through verified accuracy. Multiple agents research questions independently, their votes are weighted by on-chain Brier scores, and consensus is computed transparently on Base Sepolia. Reputation is non-transferable (soulbound NFTs), rewards are distributed by calibration weight, and every resolution makes the system more accurate.

## Why It Fits the Agent Economy Track

- **Agent reputation as a primitive** — Brier scores stored on-chain create a composable trust layer any protocol can read
- **Earned influence** — no staking, no governance tokens; agents gain weight by being right
- **Soulbound identity** — AgentIdentity.sol issues non-transferable ERC-721 tokens that accumulate reputation
- **Reward distribution** — ETH reward pools split by calibration weight (70%) + accuracy bonus (30%), using pull-payment pattern
- **Composability** — any dApp can query CalibrationRegistry for agent trust scores

## Architecture

**Off-chain (Python, zero dependencies):**
- Multi-agent parallel research (API, web search, knowledge strategies)
- Calibration-weighted linear opinion pool
- Dispute detection via weighted variance
- Self-improving: resolutions → Brier updates → DPO fine-tuning data
- Multi-vector adversarial simulation (collusion, adaptive, bribery)
- Economic security model: N×B>M formula for deployment sizing

**On-chain (Solidity, Base Sepolia):**
- `CalibrationRegistry.sol` — WAD fixed-point Brier storage + weight computation
- `SwarmConsensus.sol` — vote aggregation, weighted consensus, YES/NO/DISPUTE resolution
- `RewardDistribution.sol` — ETH reward pools with calibration-weighted distribution
- `AgentIdentity.sol` — soulbound ERC-721 agent reputation tokens with live profile aggregation

**Bridge:**
- `bridge.py` — Python↔contract CLI for seeding scores, submitting votes, verifying parity
- 14 automated parity tests ensure Python and Solidity math match exactly

## Deployed Contracts (Base Sepolia)

| Contract | Address |
|----------|---------|
| CalibrationRegistry | `0x42987D1753e6290B68273Ff8310E7f8248290890` |
| SwarmConsensus | `0xF0F393D1bFA815537F9FcfC6e6520e0379A1071a` |
| RewardDistribution | `0xa9B3bB31dbe15DD26031Fe899284F267308D625B` |
| AgentIdentity | `0x5bD8b36214d002cB250Be1c9a82022875331b947` |

## Key Metrics

- **742 Python tests + 55 Foundry tests = 797 total**
- 90 adversarial simulation tests (collusion, adaptive, bribery — all three vectors)
- 50 economic security model tests (security parameter ρ, N×B>M, minimum viable pool)
- 83 Sybil resistance tests (variance gate, registration bounds)
- 14 cross-engine parity tests (Python ↔ Solidity exact match)
- Benchmark: swarm Brier 0.0724 vs 0.1029 best single agent (50-case, seed=42)
- 3.3s end-to-end consensus on consumer hardware
- Economic security formula: N×B>M (validator count × bribery cost > market size)

## Security Analysis

The protocol ships a formal adversarial analysis (`docs/threat-model.md`):

- **Collusion:** Symmetric Collusion Lemma — W_sybil ≥ W_honest × (1 − NO_THRESHOLD) / NO_THRESHOLD ≈ 5.667 × W_honest to flip a decision. Proven and pinned by tests at k ∈ {1, 2, 5, 20}.
- **Adaptive attacker:** concentrated vote ≡ single-Sybil bound — budget splitting never helps.
- **Bribery:** in a 3-agent demo swarm, bribery ($500) is 2.7× cheaper than Sybil ($1,360). The crossover favors Sybil at ≥10 validators with $2k/agent bribery cost — documented as the hackathon → production transition requirement.
- **Economic security model** (`docs/ECONOMIC_MODEL.md`): security parameter ρ = min(C_sybil, C_bribery) / M and the invariant N×B>M. 50 tests verify the math against actual protocol constants.

## What Makes It Different

Most "AI agent" projects use agents as glorified API wrappers. Swarm Oracle creates a genuine agent economy:
- Reputation is **earned** through prediction accuracy, not bought
- Trust is **verifiable** — anyone can read the registry and compute weights
- Identity is **soulbound** — reputation can't be transferred or sold
- The system is **self-improving** — every resolution makes future predictions better
- Security is **formally analyzed** — adversarial bounds are proven and backed by executable tests
- Deployment sizing is **quantified** — N×B>M formula tells you exactly when a market is economically secure

## Interactive Demo

- **Jupyter notebook** — `notebooks/swarm_oracle_demo.ipynb`: 7-part walkthrough (calibration weights, consensus formation, benchmark, adversarial analysis, economic security, on-chain architecture, full test suite). Browser-renderable on GitHub. No LLM required.
- **CLI:** `python swarm_verify.py --demo "question"` — deterministic, no server
- **Live landing page:** https://solmonger.github.io/swarm-oracle/
- **Demo video:** https://youtu.be/Dy1h0Hcr4HQ

## Repository

https://github.com/SolMonger/swarm-oracle

## Team

Eshaan Mathakari — solo developer
