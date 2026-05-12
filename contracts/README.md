# Swarm Oracle — On-Chain Contracts

On-chain calibration registry, consensus aggregation, reward distribution, and agent identity for the Swarm Oracle protocol. These contracts mirror the Python reference implementation in `swarm_oracle/` using 18-decimal fixed-point arithmetic.

## Architecture

```
CalibrationRegistry.sol          SwarmConsensus.sol
┌─────────────────────┐         ┌──────────────────────┐
│ Per-agent Brier      │◄────────│ Reads weights for    │
│ scores + weights     │         │ vote aggregation     │
│                      │         │                      │
│ seedBrier()          │         │ submitVotes()        │
│ updateBrier()        │         │ getResult()          │
│ computeWeight()      │         │ getVotes()           │
│ computeWeights()     │         │ YES / NO / DISPUTE   │
└─────────────────────┘         └──────────────────────┘
         ▲                                ▲
         │                                │
         │         RewardDistribution.sol  │
         │        ┌──────────────────────┐│
         ├────────│ Reads weights +      ││
         │        │ consensus results    │┘
         │        │                      │
         │        │ fundQuestion()       │
         │        │ distributeRewards()  │
         │        │ withdraw()           │
         │        │ 70% base / 30% acc.  │
         │        └──────────────────────┘
         │
         │         AgentIdentity.sol
         │        ┌──────────────────────┐
         └────────│ Reads calibration    │
                  │ stats for profiles   │
                  │                      │
                  │ mint() / mintBatch() │
                  │ getAgentProfile()    │
                  │ SOULBOUND (no xfer)  │
                  └──────────────────────┘
                           ▲
                           │
    bridge.py ─── Python→Contract bridge (all 4 contracts) ──┘
```

## Contracts

### CalibrationRegistry.sol (282 lines)
Stores per-agent Brier scores and computes calibration weights in WAD (18-decimal) fixed-point. Supports incremental updates and batch seeding from off-chain history.

### SwarmConsensus.sol (301 lines)
Accepts agent votes for a question, reads calibration weights from the registry, computes weighted consensus probability, classifies the decision (YES/NO/DISPUTE), and stores the result for audit.

### RewardDistribution.sol (~250 lines)
Distributes ETH reward pools to agents after consensus resolution. Two-part split: 70% by calibration weight, 30% accuracy bonus for agents aligned with consensus. Uses pull-payment pattern (agents call `withdraw()`).

### AgentIdentity.sol (~280 lines)
Soulbound ERC-721 tokens representing agent reputation. Non-transferable by design — reputation is earned, not bought. Includes `getAgentProfile()` which aggregates token data with live calibration stats from the registry.

## Weight Formula (matches `swarm_oracle/weights.py`)

```
if numPredictions < 20:
    weight = 1.0                          # new agents get equal voice

else:
    raw        = 1 / (brier + 0.001)      # lower Brier → higher weight
    confidence = min(1, n / 100)           # more history → stronger signal
    weight     = raw × confidence
```

## Consensus (matches `swarm_oracle/consensus.py`)

Calibration-weighted linear opinion pool:

```
consensus_p = Σ (w_i / Σw) × p_i

if std(votes) > 0.20  → DISPUTE
elif consensus_p ≥ 0.85 → YES
elif consensus_p ≤ 0.15 → NO
else                     → DISPUTE
```

## Reward Distribution

```
Pool funded → Question resolved → Distribution triggered

70% BASE POOL:     Split by calibration weight
30% ACCURACY POOL: Split among agents within 0.15 of consensus
                   (fallback: split by weight if nobody aligned)

Agents call withdraw() to pull accumulated rewards.
```

## Testing

### Python parity tests (no Solidity toolchain needed)

```bash
python3 -m pytest tests/ -v
```

### Foundry tests (requires `forge`)

```bash
cd contracts
forge test -vvv
```

## Deployment

```bash
# Set environment
export BASE_SEPOLIA_RPC="https://sepolia.base.org"
export DEPLOYER_KEY="0x..."

# Deploy all 4 contracts + seed agents + mint identities
cd contracts
forge script script/Deploy.s.sol --rpc-url $BASE_SEPOLIA_RPC \
    --private-key $DEPLOYER_KEY --broadcast

# Or use the Python bridge CLI
python3 bridge.py --rpc $BASE_SEPOLIA_RPC --key $DEPLOYER_KEY \
    --registry 0x... --consensus 0x... \
    --action seed --agent 0x0001 --brier 0.10 --n 220
```

## File Map

| File | Purpose |
|------|---------|
| `src/CalibrationRegistry.sol` | Agent Brier scores, weight computation |
| `src/SwarmConsensus.sol` | Vote submission, weighted aggregation, decision |
| `src/RewardDistribution.sol` | ETH reward pools, accuracy-weighted distribution |
| `src/AgentIdentity.sol` | Soulbound ERC-721 agent reputation tokens |
| `test/CalibrationRegistry.t.sol` | Foundry unit tests — registry |
| `test/SwarmConsensus.t.sol` | Foundry unit tests — consensus |
| `test/RewardDistribution.t.sol` | Foundry unit tests — rewards |
| `test/AgentIdentity.t.sol` | Foundry unit tests — identity |
| `test/test_solidity_math_parity.py` | Cross-verification vs. Python reference |
| `script/Deploy.s.sol` | Foundry deployment script (all 4 contracts) |
| `bridge.py` | Python↔Contract bridge + CLI |
| `foundry.toml` | Foundry configuration |
| `agent_registry.json` | Agent ID → ETH address mapping |

## License

MIT
