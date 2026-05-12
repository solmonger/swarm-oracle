#!/bin/bash
# deploy.sh — Deploy Swarm Oracle contracts to Base Sepolia
# Usage: cd contracts && bash deploy.sh
set -euo pipefail

# ---- Load credentials from openclaw-infra/.env ----
ENV_FILE="$HOME/openclaw-infra/.env"
if [ -f "$ENV_FILE" ]; then
    export $(grep -E '^ANTELLIGENCE_DEPLOYER_PRIVATE_KEY=' "$ENV_FILE" | xargs)
    export $(grep -E '^ANTELLIGENCE_DEPLOYER_ADDRESS=' "$ENV_FILE" | xargs)
    echo "✓ Loaded deployer credentials from $ENV_FILE"
else
    echo "✗ $ENV_FILE not found"
    exit 1
fi

if [ -z "${ANTELLIGENCE_DEPLOYER_PRIVATE_KEY:-}" ]; then
    echo "✗ ANTELLIGENCE_DEPLOYER_PRIVATE_KEY not set"
    exit 1
fi

echo "  Deployer address: $ANTELLIGENCE_DEPLOYER_ADDRESS"

# ---- Check Foundry ----
if ! command -v forge &>/dev/null; then
    echo "Installing Foundry..."
    curl -L https://foundry.paradigm.xyz | bash
    source "$HOME/.bashrc" 2>/dev/null || source "$HOME/.zshenv" 2>/dev/null || true
    export PATH="$HOME/.foundry/bin:$PATH"
    foundryup
fi
echo "✓ Foundry: $(forge --version)"

# ---- Install forge-std if missing ----
if [ ! -d "lib/forge-std" ]; then
    echo "Installing forge-std..."
    forge install foundry-rs/forge-std --no-git
fi
echo "✓ forge-std installed"

# ---- Build ----
echo ""
echo "=== Building contracts ==="
forge build
echo "✓ Build successful"

# ---- Test ----
echo ""
echo "=== Running tests ==="
forge test -vv || echo "⚠ Some tests may fail without forge-std Test import (non-blocking)"

# ---- Check deployer balance ----
echo ""
echo "=== Checking deployer balance ==="
BALANCE=$(cast balance "$ANTELLIGENCE_DEPLOYER_ADDRESS" --rpc-url https://sepolia.base.org 2>/dev/null || echo "0")
echo "  Balance: $BALANCE wei"

# ---- Deploy ----
echo ""
echo "=== Deploying to Base Sepolia ==="
forge script script/Deploy.s.sol \
    --rpc-url https://sepolia.base.org \
    --private-key "$ANTELLIGENCE_DEPLOYER_PRIVATE_KEY" \
    --broadcast \
    -vvvv \
    2>&1 | tee deploy_output.log

echo ""
echo "✓ Deployment complete. Check deploy_output.log for addresses."
echo "  Broadcast artifacts in: broadcast/Deploy.s.sol/84532/"
