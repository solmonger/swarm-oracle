#!/usr/bin/env bash
# host-commit-run11.sh — Apply run #11 economic security model to Desktop repo
#
# Run from the host Mac terminal (not the Cowork sandbox):
#   bash ~/openclaw-infra/hackathon/swarm-oracle/scripts/host-commit-run11.sh
#
# What this does:
#   1. Verifies the Desktop repo exists
#   2. Removes stale .git/index.lock if present
#   3. Copies all run #11 new/modified files from openclaw-infra mirror → Desktop
#   4. Runs the full Python test suite (expect 613 passed, 3 skipped)
#   5. Stages and commits with a full commit message
#   6. Prints git push reminder

set -euo pipefail

DESKTOP="$HOME/Desktop/hackathon/swarm-oracle"
MIRROR="$HOME/openclaw-infra/hackathon/swarm-oracle"

echo "=== Swarm Oracle — Run #11 Host Commit Script ==="
echo ""

# 1. Verify Desktop repo
if [ ! -d "$DESKTOP/.git" ]; then
  echo "ERROR: Desktop repo not found at $DESKTOP"
  echo "Apply prior sync bundles first, or clone the repo:"
  echo "  git clone https://github.com/solmonger/swarm-oracle $DESKTOP"
  exit 1
fi
echo "✓ Desktop repo exists at $DESKTOP"

# 2. Remove stale git lock
if [ -f "$DESKTOP/.git/index.lock" ]; then
  echo "  Removing stale .git/index.lock..."
  rm -f "$DESKTOP/.git/index.lock"
fi

# 3. Copy run #11 files
echo ""
echo "Copying run #11 files from mirror to Desktop..."

# New files
cp "$MIRROR/scripts/economic_model.py"         "$DESKTOP/scripts/economic_model.py"
cp "$MIRROR/tests/test_economic_model.py"       "$DESKTOP/tests/test_economic_model.py"
cp "$MIRROR/docs/ECONOMIC_MODEL.md"             "$DESKTOP/docs/ECONOMIC_MODEL.md"

# Modified files
cp "$MIRROR/Makefile"                            "$DESKTOP/Makefile"
cp "$MIRROR/README.md"                           "$DESKTOP/README.md"
cp "$MIRROR/JUDGES.md"                           "$DESKTOP/JUDGES.md"
cp "$MIRROR/design.md"                           "$DESKTOP/design.md"
cp "$MIRROR/tests/test_repo_norms.py"            "$DESKTOP/tests/test_repo_norms.py"
cp "$MIRROR/docs/SUBMISSION_DEVNETWORK.md"       "$DESKTOP/docs/SUBMISSION_DEVNETWORK.md"
cp "$MIRROR/docs/SUBMISSION_KITEAI.md"           "$DESKTOP/docs/SUBMISSION_KITEAI.md"
cp "$MIRROR/docs/DEMO_VIDEO_SCRIPT.md"           "$DESKTOP/docs/DEMO_VIDEO_SCRIPT.md"

echo "✓ All run #11 files copied"

# 4. Run test suite
echo ""
echo "Running Python test suite..."
cd "$DESKTOP"
python3 -m pytest tests/ -q --tb=short
echo ""
echo "✓ Tests passed"

# 5. Stage and commit
echo ""
echo "Staging changes..."
git add \
  scripts/economic_model.py \
  tests/test_economic_model.py \
  docs/ECONOMIC_MODEL.md \
  Makefile \
  README.md \
  JUDGES.md \
  design.md \
  tests/test_repo_norms.py \
  docs/SUBMISSION_DEVNETWORK.md \
  docs/SUBMISSION_KITEAI.md \
  docs/DEMO_VIDEO_SCRIPT.md

echo "Committing..."
git commit -m "feat(security): economic security model with 613 tests total

Run #11 (automated, Cowork scheduled loop).

## New: Economic Security Model

### New files
- scripts/economic_model.py — formal economic security analysis
  - ValidatorProfile dataclass with weight property
  - sybil_attack_cost() — minimum Sybils and USD cost to flip consensus
  - bribery_attack_cost() — greedy minimum bribery cost
  - security_parameter() — composite security metric (ρ = min_attack / market)
  - pool_size_scaling() and market_size_scaling() — tabular analysis
  - minimum_viable_pool_for_market() — binary search for smallest secure pool
  - CLI: python3 -m scripts.economic_model [--pool-scaling] [--market-scaling] [--mvp] [--json]

- tests/test_economic_model.py — 50 tests across 10 classes
  - TestWeightFormulaParity — 11 tests verifying parity with weights.py
  - TestValidatorProfile — 2 tests
  - TestSybilAttackCost — 6 tests (formula correctness, monotonicity)
  - TestBriberyAttackCost — 6 tests (greedy optimality, thresholds)
  - TestSecurityParameter — 7 tests (ratio def, secure/insecure, crossover)
  - TestPoolSizeScaling — 3 tests
  - TestMarketSizeScaling — 3 tests
  - TestMinimumViablePool — 4 tests
  - TestCLIOutput — 6 tests
  - TestPublicSurface — 2 tests (constants match protocol)

- docs/ECONOMIC_MODEL.md — 11-section formal doc
  - Protocol parameters and weight formula
  - Sybil attack cost derivation (W_sybil ≥ W_honest × 5.667)
  - Bribery attack cost (greedy, proof of optimality)
  - Security parameter ρ = min(C_sybil, C_bribery) / M
  - Crossover analysis (B* ≈ avg_weight × 5.667 × 3 × C_reg)
  - Scaling tables: pool size 1–200, market size \$1K–\$1M
  - Production formula: N × B > M (necessary condition for security)
  - Phase 1/2/3 recommendations (hackathon → testnet → mainnet)
  - Limitations: variance-gate, correlated failures, front-running, governance

### Modified files
- Makefile: + test-economic, economic-model, economic-model-scaling, economic-model-mvp targets
- README.md: + Economic Security Model section; test count 613
- JUDGES.md: + economic-model-mvp as step 7 in verify-yourself; + economic model in What's Novel
- design.md: + economic model stats (613 tests, 668 total)
- tests/test_repo_norms.py: + TestEconomicModelDoc (14 tests), TestEconomicModelMakefileTargets (5), TestReadmeEconomicModelReference (3) — 22 new tests
- docs/SUBMISSION_DEVNETWORK.md: 613 tests, + economic model bullet in security section
- docs/SUBMISSION_KITEAI.md: 613 tests, 668 total, + economic model metrics
- docs/DEMO_VIDEO_SCRIPT.md: 613 tests throughout

## Headline Result

The key production formula derived and backed by tests:

    Security condition:  N × B > M
    Minimum pool:        N ≥ ⌈M / B⌉

    (N = validator count, B = per-agent bribery cost USD, M = market size USD)

Reproduce: make economic-model-mvp

## Test Counts
Previous total: 541 Python, 55 Foundry
This run adds:  50 (test_economic_model.py) + 22 (test_repo_norms additions) = 72
New total:      613 Python + 55 Foundry = 668 total"

echo ""
echo "✓ Committed"
echo ""
echo "=== NEXT STEPS ==="
echo "  git push origin main"
echo "  → judges see updated test count (613), economic model doc, economic-model-mvp output"
echo ""
echo "Optional:"
echo "  make economic-model-mvp     # see min viable pool per market tier"
echo "  make economic-model-scaling # see security vs pool-size and market-size tables"
echo "  Update DevPost: test count 541→613, add economic security model mention"
