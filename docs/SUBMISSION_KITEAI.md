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

- 108 Python tests + Foundry test suite
- 29 scored real-world forecasts, mean Brier 0.157
- 3.3s end-to-end consensus on consumer hardware
- Bit-for-bit parity between Python and Solidity math

## What Makes It Different

Most "AI agent" projects use agents as glorified API wrappers. Swarm Oracle creates a genuine agent economy:
- Reputation is **earned** through prediction accuracy, not bought
- Trust is **verifiable** — anyone can read the registry and compute weights
- Identity is **soulbound** — reputation can't be transferred or sold
- The system is **self-improving** — every resolution makes future predictions better

## Repository

https://github.com/SolMonger/swarm-oracle

## Team

Eshaan Mathakari — solo developer
