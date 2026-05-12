#!/usr/bin/env python3
"""Top-level entry point for the Week-1 Swarm Oracle demo.

Usage:
    python swarm_verify.py "Did BTC close above 100K on May 5?"

Equivalent to `python -m swarm_oracle "..."`.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make the package importable when running from a checkout.
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from swarm_oracle.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
