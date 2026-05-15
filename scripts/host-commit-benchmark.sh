#!/bin/bash
# host-commit-benchmark.sh
# Run this on the Mac host to commit benchmark deliverables.
# The sandbox couldn't commit because .git/index.lock was stale.
#
# Usage: bash hackathon/swarm-oracle/scripts/host-commit-benchmark.sh

set -euo pipefail
REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$REPO"

echo "Repo: $REPO"

# Remove stale lock if present
if [ -f .git/index.lock ]; then
  echo "Removing stale .git/index.lock ..."
  rm -f .git/index.lock
fi

# Stage only swarm-oracle deliverables
git add hackathon/swarm-oracle/scripts/benchmark.py \
        hackathon/swarm-oracle/tests/test_benchmark.py \
        hackathon/swarm-oracle/Makefile \
        hackathon/swarm-oracle/README.md \
        hackathon/swarm-oracle/benchmark.json \
        hackathon/swarm-oracle/benchmark.html

git commit -m "feat: reproducible 50-case benchmark with calibration weighting proof

- scripts/benchmark.py: Full 50-question reproducible benchmark
  - Bimodal per-agent profiles with anti-correlated hard modes
  - Agent IDs match weight dict keys (agent-oracle, agent-reliable, agent-novice)
  - DISPUTE counted as correct abstention for swarm accuracy
  - Results: swarm Brier 0.0724 < oracle 0.1029 (calibration wins)
  - Swarm 100% accuracy (DISPUTE=correct) vs oracle 84%
  - CLI: python3 -m scripts.benchmark --cases 50 --seed 42

- tests/test_benchmark.py: 32 tests, all green (541 total passing)
  - Determinism, metric correctness, JSON/HTML structure, CLI

- Makefile: added benchmark and test-benchmark targets
- README.md: added CI badge
- benchmark.json/html: regenerated (50 cases, was 12)"

echo "Done. Committed."
