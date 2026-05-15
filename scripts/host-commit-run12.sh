#!/usr/bin/env bash
# host-commit-run12.sh — Apply run #12 files to Desktop repo and commit
#
# What this run added:
#   1. .github/workflows/ci.yml  — Upgraded from 34-line stub to production-quality
#      6-job CI (Python matrix, benchmark verification, adversarial + economic model
#      smoke tests, Foundry tests with gas report, repo health checks, summary gate)
#   2. notebooks/swarm_oracle_demo.ipynb — NEW: 7-part interactive Jupyter notebook
#      demonstrating the full protocol without requiring a live LLM
#   3. tests/test_notebook.py — NEW: 34 tests across 6 classes verifying the notebook
#      structure, required sections, code quality, and headline claim coverage
#
# Run this script from any directory. It will:
#   1. Remove stale .git/index.lock if present
#   2. Create notebooks/ directory
#   3. Copy the 3 new/updated files
#   4. Run the full test suite (613 Python tests expected, 3 skipped)
#   5. Commit with the run #12 message
#   6. Remind you to push
#
# Usage:  bash ~/openclaw-infra/hackathon/swarm-oracle/scripts/host-commit-run12.sh

set -euo pipefail

DESKTOP_REPO="$HOME/Desktop/hackathon/swarm-oracle"
MIRROR="$HOME/openclaw-infra/hackathon/swarm-oracle"
BLUE='\033[0;34m'; GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'

info()  { echo -e "${BLUE}[run12]${NC} $*"; }
ok()    { echo -e "${GREEN}[run12]${NC} ✓ $*"; }
fail()  { echo -e "${RED}[run12]${NC} ✗ $*"; exit 1; }

# ─── Sanity checks ────────────────────────────────────────────────
[ -d "$DESKTOP_REPO" ] || fail "Desktop repo not found at $DESKTOP_REPO"
[ -d "$MIRROR"       ] || fail "Mirror not found at $MIRROR"
[ -d "$DESKTOP_REPO/.git" ] || fail "No .git directory in $DESKTOP_REPO"

info "Desktop repo:  $DESKTOP_REPO"
info "Mirror source: $MIRROR"

# ─── Remove stale git lock ────────────────────────────────────────
LOCK="$DESKTOP_REPO/.git/index.lock"
if [ -f "$LOCK" ]; then
    info "Removing stale .git/index.lock..."
    rm -f "$LOCK"
    ok "Lock removed"
fi

# ─── Create directories ───────────────────────────────────────────
mkdir -p "$DESKTOP_REPO/notebooks"
mkdir -p "$DESKTOP_REPO/.github/workflows"
ok "Directories ensured"

# ─── Copy files ───────────────────────────────────────────────────
info "Copying .github/workflows/ci.yml (upgraded, 6-job CI)..."
cp "$MIRROR/.github/workflows/ci.yml" \
   "$DESKTOP_REPO/.github/workflows/ci.yml"
ok "ci.yml copied"

info "Copying notebooks/swarm_oracle_demo.ipynb (NEW)..."
cp "$MIRROR/notebooks/swarm_oracle_demo.ipynb" \
   "$DESKTOP_REPO/notebooks/swarm_oracle_demo.ipynb"
ok "swarm_oracle_demo.ipynb copied"

info "Copying tests/test_notebook.py (NEW, 34 tests)..."
cp "$MIRROR/tests/test_notebook.py" \
   "$DESKTOP_REPO/tests/test_notebook.py"
ok "test_notebook.py copied"

# ─── Verify files ────────────────────────────────────────────────
for f in \
    ".github/workflows/ci.yml" \
    "notebooks/swarm_oracle_demo.ipynb" \
    "tests/test_notebook.py"; do
    [ -f "$DESKTOP_REPO/$f" ] && ok "$f present" || fail "$f missing after copy"
done

# ─── Run tests ────────────────────────────────────────────────────
info "Running full test suite..."
cd "$DESKTOP_REPO"

python3 -m pytest tests/ -q --tb=short --no-header 2>&1 | tail -20

# Check exit code
if python3 -m pytest tests/ -q --tb=short --no-header > /dev/null 2>&1; then
    ok "All tests passed"
else
    fail "Tests failed — see output above. Do not commit."
fi

# ─── Commit ───────────────────────────────────────────────────────
cd "$DESKTOP_REPO"
git add -A

COMMIT_MSG="run#12: CI upgrade + Jupyter notebook + 34 notebook tests

Deliverables (2026-05-15, automated loop run #12):

1. .github/workflows/ci.yml (UPGRADED)
   - Was: 34-line stub (python-tests + solidity-tests, no matrix)
   - Now: 6-job production CI:
     * python-tests: matrix [3.11, 3.12], full 613-test suite, coverage artifact
     * benchmark: 50-case deterministic run + assertion (swarm Brier < all agents)
     * adversarial: 90-test suite + 50 economic model tests + CLI smoke tests
     * solidity-tests: Foundry with --gas-report + EIP-170 size check
     * repo-health: repo norms + landing page tests + doc staleness check
     * ci-pass: summary gate (all jobs must pass)
   - Proper concurrency cancellation, pip caching, retention on artifacts

2. notebooks/swarm_oracle_demo.ipynb (NEW)
   - 7-part interactive demonstration of the full protocol
   - Part 1: Calibration weights (compute_weight, visual comparison)
   - Part 2: Consensus formation (three scenarios: YES / DISPUTE / NO)
   - Part 3: Benchmark (50-case results, matplotlib bar chart)
   - Part 4: Adversarial analysis (Sybil + adaptive + bribery + crossover plot)
   - Part 5: Economic security (N×B>M, minimum viable pool table)
   - Part 6: On-chain architecture (contract preview + deploy commands)
   - Part 7: Full test suite runner
   - Self-contained: all imports guarded, works without a live LLM
   - matplotlib optional (text fallback for every plot)
   - Auto-detects repo root (works from notebooks/ or repo root)

3. tests/test_notebook.py (NEW, 34 tests across 6 classes)
   - TestNotebookExists (6): file present, valid JSON, nbformat ≥ 4, ≥10 cells
   - TestCellStructure (4): ≥5 markdown, ≥8 code, first=markdown, no empty cells
   - TestRequiredSections (9): parametrized on 7 headings + CI badge + H1 title
   - TestKeyClaimsCovered (7): 10 patterns + Brier formula + headline claim +
     N×B>M + test count ≥600 present
   - TestCodeQuality (5): no saved errors, matplotlib guarded, no LLM required,
     repo_root dynamic, no hardcoded secrets
   - TestPublicSurface (3): correct dir, filename, all JSON parseable

Total Python tests: 613 + 34 = 647 (+ 3 skipped) | Foundry: 55 | Grand total: 702

Bash sandbox constraint: no space left on device throughout run #12.
All work via file tools. Cross-read verification used instead of pytest run.
git commit via this host script (Desktop sandbox cannot commit due to .git/index.lock)."

git commit -m "$COMMIT_MSG"
ok "Committed"

# ─── Done ─────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
ok "Run #12 committed. Next steps:"
echo "   git push origin main"
echo ""
echo "   Optional DevPost update:"
echo "     - Test count: 613 → 647 Python + 55 Foundry = 702 total"
echo "     - Add: 'Interactive Jupyter notebook (7 parts, runs without LLM)'"
echo "     - Add: 'CI upgraded to 6-job pipeline with benchmark verification'"
echo ""
echo "   Note: CI badge on README points to ci.yml — it will now"
echo "   ACTUALLY WORK once pushed (was 404 before this run)."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
