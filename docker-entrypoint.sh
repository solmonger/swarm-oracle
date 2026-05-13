#!/bin/bash
set -euo pipefail

case "${1:-api}" in
  api)
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║  SWARM ORACLE API — http://localhost:8000                   ║"
    echo "║  Docs: http://localhost:8000/docs                           ║"
    echo "║  Interactive demo: open demo.html in a browser              ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    exec python -m uvicorn swarm_oracle.api:app --host 0.0.0.0 --port 8000
    ;;
  demo)
    echo "Running demo mode (no LLM required)..."
    python swarm_verify.py --demo "Did BTC close above \$100K on May 5, 2026?"
    echo ""
    python swarm_verify.py --demo "Will the Lakers win tonight?"
    echo ""
    python swarm_verify.py --demo --json "Is climate change accelerating?"
    ;;
  test)
    echo "Running full test suite..."
    python -m pytest tests/ -v --tb=short
    ;;
  cli)
    shift
    python swarm_verify.py --demo "$@"
    ;;
  shell)
    exec /bin/bash
    ;;
  *)
    exec "$@"
    ;;
esac
