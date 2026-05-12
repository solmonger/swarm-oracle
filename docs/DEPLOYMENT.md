# Deploying Swarm Oracle Contracts to Base Sepolia

Step-by-step guide for deploying the full Swarm Oracle contract suite to Base Sepolia testnet.

## Prerequisites

- [Foundry](https://book.getfoundry.sh/getting-started/installation) installed (`foundryup`)
- Base Sepolia ETH from a faucet:
  - https://www.coinbase.com/faucets/base-ethereum-goerli-faucet
  - https://faucet.quicknode.com/base/sepolia
  - https://sepolia-faucet.com/
- A deployer wallet with its private key

## 1. Set Environment Variables

```bash
# Your deployer wallet private key (keep secret!)
export PRIVATE_KEY="0x..."

# Base Sepolia RPC endpoint (free tier from any of these)
export BASE_SEPOLIA_RPC="https://sepolia.base.org"
# or: https://base-sepolia.blockpi.network/v1/rpc/public
# or: Alchemy/Infura if you have a key
```

## 2. Compile Contracts

```bash
cd contracts
forge build
```

Expected output: 4 contracts compiled successfully:
- `CalibrationRegistry.sol` — Brier score storage + weight computation (WAD math)
- `SwarmConsensus.sol` — On-chain weighted consensus aggregation
- `RewardDistribution.sol` — ETH reward pool with calibration-weighted splits
- `AgentIdentity.sol` — Soulbound ERC-721 reputation tokens

## 3. Run Foundry Tests

```bash
forge test -vv
```

All 53 Solidity tests should pass before deploying.

## 4. Deploy

The `Deploy.s.sol` script deploys all 4 contracts, seeds 3 mock agents with Brier scores, and mints soulbound identity tokens.

```bash
forge script script/Deploy.s.sol:DeploySwarmOracle \
    --rpc-url $BASE_SEPOLIA_RPC \
    --private-key $PRIVATE_KEY \
    --broadcast \
    --verify \
    --etherscan-api-key $BASESCAN_API_KEY \
    -vvvv
```

If you don't have a Basescan API key, drop `--verify` and `--etherscan-api-key`:

```bash
forge script script/Deploy.s.sol:DeploySwarmOracle \
    --rpc-url $BASE_SEPOLIA_RPC \
    --private-key $PRIVATE_KEY \
    --broadcast \
    -vvvv
```

## 5. Record Deployed Addresses

After deployment, Foundry prints the contract addresses. Update `contracts/agent_registry.json`:

```json
{
  "calibration_registry": "0x<DEPLOYED_ADDRESS>",
  "swarm_consensus": "0x<DEPLOYED_ADDRESS>",
  "reward_distribution": "0x<DEPLOYED_ADDRESS>",
  "agent_identity": "0x<DEPLOYED_ADDRESS>",
  "chain_id": 84532,
  "network": "base-sepolia"
}
```

## 6. Verify Python↔Solidity Bridge

Once deployed, verify the bridge connects properly:

```bash
# Install chain deps
pip install 'swarm-oracle[chain]'

# Set RPC
export WEB3_PROVIDER_URI="https://sepolia.base.org"

# Test bridge connectivity
python -c "
from contracts.bridge import SwarmBridge
bridge = SwarmBridge(
    rpc_url='$BASE_SEPOLIA_RPC',
    registry_addr='0x<REGISTRY>',
    consensus_addr='0x<CONSENSUS>'
)
print('Registry connected:', bridge.get_agent_count())
"
```

## 7. Run Full Pipeline (CLI → Chain)

```bash
export LLM_API_URL="http://localhost:8080/v1/chat/completions"

python swarm_verify.py --on-chain \
    --registry-addr 0x<REGISTRY> \
    --consensus-addr 0x<CONSENSUS> \
    "Did BTC close above \$100K on May 5, 2026?"
```

This runs the swarm off-chain, then submits the consensus result on-chain for independent verification.

## 8. Verify on Basescan

View your contracts on Base Sepolia explorer:

```
https://sepolia.basescan.org/address/0x<CONTRACT_ADDRESS>
```

## Contract Sizes

| Contract | ~Size | Gas (deploy) |
|----------|-------|-------------|
| CalibrationRegistry | ~4 KB | ~800K |
| SwarmConsensus | ~3.5 KB | ~700K |
| RewardDistribution | ~5 KB | ~1M |
| AgentIdentity | ~6 KB | ~1.2M |

Total deployment cost: ~3.7M gas ≈ 0.001 ETH on Base Sepolia.

## Troubleshooting

**"Insufficient funds"** — Get more testnet ETH from a faucet. You need ~0.01 ETH for deployment + gas.

**"Nonce too low"** — Another transaction is pending. Wait or use `--nonce <N>`.

**"Contract verification failed"** — The Basescan API can be slow. Retry after a few minutes, or verify manually at https://sepolia.basescan.org.

**"forge: command not found"** — Install Foundry: `curl -L https://foundry.paradigm.xyz | bash && foundryup`.
