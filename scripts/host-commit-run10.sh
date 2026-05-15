#!/bin/bash
# host-commit-run10.sh
# Run this on the Mac host to apply run #10 doc-sync and commit.
# Run #10: Updated all stale test counts (509→541) and benchmark numbers
# (12-case 91.7%/0.0859 → 50-case 100%/0.0724) across every judge-facing file.
#
# FIRST: ensure runs #6–#9 sync bundles have been applied to Desktop repo.
# THEN: run this script from ~/Desktop/hackathon/swarm-oracle/
#
# Usage:
#   cd ~/Desktop/hackathon/swarm-oracle
#   bash ~/openclaw-infra/hackathon/swarm-oracle/scripts/host-commit-run10.sh

set -euo pipefail
DESKTOP_REPO="$HOME/Desktop/hackathon/swarm-oracle"
MIRROR="$HOME/openclaw-infra/hackathon/swarm-oracle"

if [ ! -d "$DESKTOP_REPO/.git" ]; then
  echo "ERROR: Desktop repo not found at $DESKTOP_REPO"
  exit 1
fi

cd "$DESKTOP_REPO"

# Remove stale lock if present
if [ -f .git/index.lock ]; then
  echo "Removing stale .git/index.lock ..."
  rm -f .git/index.lock
fi

echo "Copying run #10 files from openclaw-infra mirror..."

# Core judge-facing files updated this run
cp "$MIRROR/JUDGES.md"                           ./JUDGES.md
cp "$MIRROR/README.md"                           ./README.md
cp "$MIRROR/index.html"                          ./index.html
cp "$MIRROR/design.md"                           ./design.md
cp "$MIRROR/tests/test_landing_page.py"          ./tests/test_landing_page.py
cp "$MIRROR/docs/SUBMISSION_DEVNETWORK.md"       ./docs/SUBMISSION_DEVNETWORK.md
cp "$MIRROR/docs/SUBMISSION_KITEAI.md"           ./docs/SUBMISSION_KITEAI.md
cp "$MIRROR/docs/DEMO_VIDEO_SCRIPT.md"           ./docs/DEMO_VIDEO_SCRIPT.md
cp "$MIRROR/docs/competitive-comparison.md"      ./docs/competitive-comparison.md

echo "Files copied. Running tests..."
python3 -m pytest tests/ -q --tb=short

echo ""
echo "Staging run #10 changes..."
git add \
  JUDGES.md \
  README.md \
  index.html \
  design.md \
  tests/test_landing_page.py \
  docs/SUBMISSION_DEVNETWORK.md \
  docs/SUBMISSION_KITEAI.md \
  docs/DEMO_VIDEO_SCRIPT.md \
  docs/competitive-comparison.md

git commit -m "docs: sync all test counts 509→541 and benchmark numbers to 50-case results

Run #10 doc pass — all judge-facing files now show accurate numbers from
the reproducible 50-case benchmark (seed=42) built in run #9.

Changes:
- JUDGES.md: headline table now shows 50-case numbers (swarm 100%/0.0724 Brier
  vs old 12-case 91.7%/0.0859); explains DISPUTE-as-correct-abstention;
  test count 509→541
- README.md: test counts 154→541 in Testing section
- index.html: stat cards updated (91.7%→100%, 0.0859→0.0724, 509→541);
  benchmark table fully updated to 50-case numbers with new narrative;
  SVG caption and quickstart block updated
- design.md: stat card example, current-stats table updated (509→541,
  564→596 total, accuracy note updated)
- tests/test_landing_page.py: assertions updated for new headline numbers
  (100%, 0.0724, 541)
- docs/SUBMISSION_DEVNETWORK.md: 509→541 Python tests
- docs/SUBMISSION_KITEAI.md: 509→541 Python, 564→596 total
- docs/DEMO_VIDEO_SCRIPT.md: 509→541 throughout, benchmark accuracy updated
- docs/competitive-comparison.md: 0.0859→0.0724 Brier, 91.7%→100% accuracy

No code changes. Zero regressions expected (test assertions updated to match)."

echo ""
echo "Done. Push with: git push origin main"
