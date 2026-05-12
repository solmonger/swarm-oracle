# Swarm Oracle — On-Chain Contracts

On-chain calibration registry and consensus aggregation for the Swarm Oracle protocol. These contracts mirror the Python reference implementation in `swarm_oracle/` using 18-decimal fixed-point arithmetic.

## Architecture

```
CalibrationRegistry.sol          SwarmConsensus.sol
┌─────────────────────┐         ┌──────────────────────┐
│ Per-agent Brier      │◄────────│ Reads weights for    │
│ scores + weights     │         │ vote aggregation     │
│                      │         │                      │
│ seedBrier()          │         │ submitVotes()        │
│ updateBrier()        │         │ getResult()          │
│ computeWeight()      │         │                      │
│ computeWeights()     │         │ YES / NO / DISPUTE   │
└─────────────────────┘         └──────────────────────┘
         ▲                                ▲
         │                                │
    bridge.py ─── Python→Contract bridge ──┘
```

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

## Testing

### Python parity tests (no Solidity toolchain needed)

```bash
python3 contracts/test/test_solidity_math_parity.py
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

# Deploy via Foundry
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
| `test/CalibrationRegistry.t.sol` | Foundry unit tests |
| `test/test_solidity_math_parity.py` | Cross-verification vs. Python reference |
| `script/Deploy.s.sol` | Foundry deployment script |
| `bridge.py` | Python↔Contract bridge + CLI |
| `foundry.toml` | Foundry configuration |

## License

MIT
