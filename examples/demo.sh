#!/usr/bin/env bash
set -euo pipefail

# Swarm Oracle — Quick Demo
# Requires a local OpenAI-compatible LLM server.
# Set LLM_API_URL to point at your server, or default to localhost:8080.

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

echo "============================================"
echo "  Swarm Oracle — Calibration-Weighted Demo"
echo "============================================"
echo ""

if [ -z "${LLM_API_URL:-}" ]; then
    echo "No LLM_API_URL set — using default http://localhost:8080/v1/chat/completions"
    echo "Start a local LLM server first (llama.cpp, Ollama, vLLM, etc.)"
    echo ""
fi

QUESTION="${1:-Will Bitcoin be above \$100,000 on June 1, 2026?}"

echo "Question: $QUESTION"
echo ""

python swarm_verify.py "$QUESTION"

echo ""
echo "--- JSON output ---"
python swarm_verify.py --json "$QUESTION" | python -m json.tool
