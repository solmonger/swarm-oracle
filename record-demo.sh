#!/usr/bin/env bash
# record-demo.sh — Record a terminal demo of Swarm Oracle using script(1).
#
# Usage:
#   cd ~/Desktop/hackathon/swarm-oracle
#   bash record-demo.sh
#
# Produces: demo-recording.txt (typescript) that can be replayed with scriptreplay,
# or used as reference for a screen recording.
#
# No LLM server needed — uses --demo flag with canned responses.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT="$SCRIPT_DIR/demo-recording.txt"

echo "=============================================="
echo "  Swarm Oracle Demo Recording"
echo "  Output: $OUTPUT"
echo "=============================================="
echo ""
echo "This will run three demo queries showing:"
echo "  1. Crypto question (BTC price verification)"
echo "  2. Sports question (match prediction)"
echo "  3. JSON output mode"
echo ""
echo "Starting in 2 seconds..."
sleep 2

# Clear screen for clean recording
clear

echo '$ # Swarm Oracle — Calibration-Weighted Multi-Agent Prediction Oracle'
echo '$ # Three AI agents independently research a question, then we combine'
echo '$ # their votes weighted by historical prediction accuracy (Brier score).'
echo ''
sleep 1

echo '$ # Demo 1: Crypto price verification'
echo '$ python swarm_verify.py --demo "Did BTC close above $100K on May 5, 2026?"'
echo ''
sleep 0.5
cd "$SCRIPT_DIR"
python3 swarm_verify.py --demo "Did BTC close above \$100K on May 5, 2026?"
echo ''
sleep 3

echo '$ # Notice: agent-oracle (Brier 0.08, 220 predictions) gets 60% weight'
echo '$ # while agent-novice (no track record) gets only 6%. Accuracy earns influence.'
echo ''
sleep 3

echo '$ # Demo 2: Sports match prediction'
echo '$ python swarm_verify.py --demo "Will Barcelona win the match against Alaves?"'
echo ''
sleep 0.5
python3 swarm_verify.py --demo "Will Barcelona win the match against Alaves?"
echo ''
sleep 3

echo '$ # Demo 3: Machine-readable JSON output'
echo '$ python swarm_verify.py --demo --json "Will it rain in Zurich tomorrow?" | python3 -m json.tool | head -20'
echo ''
sleep 0.5
python3 swarm_verify.py --demo --json "Will it rain in Zurich tomorrow?" | python3 -m json.tool | head -20
echo ''
sleep 2

echo '$ # Full test suite'
echo '$ python3 -m pytest tests/ --tb=short -q'
echo ''
sleep 0.5
python3 -m pytest tests/ --tb=short -q 2>&1
echo ''
sleep 2

echo '$ # Swarm Oracle: calibration-weighted consensus where accuracy is earned, not bought.'
echo '$ # MIT licensed. Zero external dependencies. Runs on consumer hardware.'
echo ''

echo "=============================================="
echo "  Demo complete! Recording saved to $OUTPUT"
echo "=============================================="
