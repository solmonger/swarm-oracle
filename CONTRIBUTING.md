# Contributing to Swarm Oracle

Thanks for your interest. Swarm Oracle is a hackathon project that is also a
serious open-source attempt — we treat contribution standards the same as
any production codebase. This document covers the dev environment, the test
expectations, and the PR flow.

## Quick start

```bash
git clone https://github.com/<your-fork>/swarm-oracle.git
cd swarm-oracle

# Python — Python 3.10 or newer.
pip install -e .            # installs the `swarm_oracle` package + deps
pip install pytest fastapi httpx uvicorn

# Solidity — Foundry.
curl -L https://foundry.paradigm.xyz | bash
foundryup
cd contracts && forge install && cd ..

# Sanity: full test suite should pass on a clean checkout.
python -m pytest tests/ -v
cd contracts && forge test -v && cd ..
```

Docker users can skip the local Python install:

```bash
docker compose run --rm oracle test   # 200+ tests, 31s
docker compose up                     # API on :8000
```

## Where the code lives

```
swarm_oracle/        Pure-Python protocol engine (consensus, weights, sybil, …)
contracts/           Foundry-managed Solidity contracts + parity tests
tests/               Python pytest suite — must stay green on every PR
scripts/             CLIs (sybil_demo, benchmark — invoked via -m)
docs/                Long-form writeups (architecture, security model, …)
examples/            Self-contained example scripts for new contributors
```

The dependency arrow is one-way: contracts mirror Python math, Python does
not import from contracts. See `docs/architecture.svg` for the full picture
and `docs/security-model.md` for the protocol's threat model.

## Tests are the contract

Every PR is expected to pass:

1. `python -m pytest tests/ -v` — 200+ tests across the protocol engine,
   API, on-chain bridge parity, and design system.
2. `cd contracts && forge test -v` — 55 Solidity tests for the four
   on-chain contracts.

If your PR adds a feature, it must add tests that fail without your change.
If your PR fixes a bug, it must add a regression test for that specific
bug.

Coverage targets (informational, not gated):

- Each new pure function in `swarm_oracle/` should have at least one
  happy-path test plus boundary tests (empty input, single-element input,
  unit-interval boundaries where applicable).
- New CLIs in `scripts/` should be tested as subprocesses for at least the
  text and JSON output paths.
- New contracts should be tested with both `forge test` and a Python
  parity test in `tests/test_on_chain.py`.

## Style and architecture

- **No external CSS or JS CDN.** The submission asset table promises a
  zero-network landing page; see `tests/test_landing_page.py` for the
  enforcement of this rule.
- **Design tokens are canonical.** New UI surfaces (HTML in `swarm_oracle/`,
  README badges, generated reports) must use the tokens declared in
  `design.md`. The `tests/test_design_system.py` suite verifies token
  parity across every shipped surface.
- **Pure functions in the protocol engine.** `swarm_oracle/consensus.py`,
  `weights.py`, `sybil.py` are intentionally I/O-free so they can be
  exhaustively tested. Side effects live in `agent.py`, `api.py`, and
  `cli.py`.
- **No `print` in library code.** Use the FastAPI logger from `api.py` or
  raise an exception. CLI scripts can `print` freely.
- **Decisions go in the vault, not the source tree.** Architectural
  decisions (why a formula, why a threshold) belong in
  `~/Documents/Jarvis's Vault/decisions/` (the project's design ledger).
  Code comments should explain *what* the code does; the *why* lives in
  the vault.

## PR flow

1. Fork the repo and create a feature branch
   (`feat/sybil-cap-table`, `fix/variance-edge-case`, etc.).
2. Run the full test suite locally before pushing — CI runs the same
   commands and we don't want to find out about regressions in PR review.
3. Open a PR with a description that covers:
   - What changed and why
   - What tests were added / updated
   - Any impact on the security model (`docs/security-model.md`),
     design system (`design.md`), or on-chain contracts
4. The CI workflow at `.github/workflows/ci.yml` will run Python + Solidity
   tests on Python `3.10`, `3.11`, and `3.12`. All three must be green.
5. After approval, squash-merge to `main`. The GitHub Pages workflow at
   `.github/workflows/pages.yml` will rebuild and redeploy automatically.

## Reporting security issues

Please do not file public issues for vulnerabilities. See
[`SECURITY.md`](SECURITY.md) for the coordinated-disclosure process.

## Code of conduct

We expect contributors to be kind, focused, and honest. Personal attacks,
harassment, or attempts to bypass review get a one-warning policy and then
a permanent ban. The maintainer is reachable at the address in
[`SECURITY.md`](SECURITY.md) for any concern.

## What's most welcome

If you're looking for somewhere to start:

- **Adversarial scenario sets** for `swarm_oracle/sybil.py` — the protocol
  has been analyzed against constant-vote Sybils; we'd love more
  sophisticated attacker models (adaptive, collusion, time-varying).
- **More Foundry tests for `SwarmConsensus.sol`** — Solidity-side
  parametric variance tests would tighten the on-chain parity guarantees.
- **Connectors to additional prediction markets** beyond the Polymarket
  case we ship — Kalshi, Manifold, Augur all have public APIs.
- **Calibration datasets.** The protocol assumes a registry of Brier
  scores; richer historical data improves the headline numbers.

PRs that improve correctness, security, or developer ergonomics are
welcome at any size. PRs that add dependencies (especially CDN-served
ones) will be asked to justify the addition against the zero-network
landing-page rule.
