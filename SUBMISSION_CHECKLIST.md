# Swarm Oracle — Submission Checklist

**Deadline:** May 18, 2026  
**Today:** May 17, 2026 — LAST DAY BEFORE DEADLINE  
**Status:** Code complete. 797 tests (742 Python + 55 Foundry), 0 failures. Operator actions required.

---

## P0 — Do These Now (May 17)

### Step 1: Apply all mirror files to Desktop repo (ONE command)

```bash
bash ~/openclaw-infra/hackathon/swarm-oracle/scripts/host-commit-final.sh
```

This single script:
- Copies ALL ~40 files from the `openclaw-infra` mirror to `~/Desktop/hackathon/swarm-oracle/`
- Fixes stale test counts in the Jupyter notebook (668→742, 613→647)
- Verifies all 8 required Makefile targets are present
- Runs the full Python test suite (expect 738+ passed, 0 failed, ≤3 skipped)
- Smoke-tests `make benchmark`, `make test-parity`, `make economic-model-mvp`
- Verifies `benchmark.json` — swarm Brier < all baselines
- Commits with a comprehensive message documenting all 22 runs

### Step 2: Push to GitHub

```bash
cd ~/Desktop/hackathon/swarm-oracle
git push origin main
```

After this push:
- ✅ CI badge fires (6-job pipeline: python-tests × 2, benchmark, adversarial, solidity, repo-health)
- ✅ Jupyter notebook renders in GitHub browser (browser-renderable, no installation)
- ✅ GitHub Pages updates: `solmonger.github.io/swarm-oracle/` shows live landing page
- ✅ `make benchmark`, `make test-parity`, `make economic-model-mvp` all work for judges

### Step 3: Regenerate benchmark (if CI shows a different Brier than 0.0724)

```bash
cd ~/Desktop/hackathon/swarm-oracle
make benchmark
git add benchmark.json benchmark.html
git commit -m "regenerate benchmark: 50 cases seed=42"
git push
```

---

## P0 — Submission Forms (May 16–17)

### Step 4: Update DevPost

URL: https://devpost.com/software/swarm-oracle

Changes to make:
- **Test count:** update to "797 (742 Python + 55 Foundry)"
- **What we built:** copy from `docs/SUBMISSION_DEVNETWORK.md` (already complete and up-to-date)
- **Add:** "Interactive Jupyter notebook — 7-part walkthrough, browser-renderable on GitHub, no LLM required"
- **Add:** "6-job CI pipeline including live benchmark assertion (swarm Brier < all agents, every push)"
- **Add:** "Adversarial analysis: Symmetric Collusion Lemma, bribery/Sybil crossover, 90 pinned tests"
- **Add:** "Economic security model: N×B>M formula, ρ parameter, 50 tests"

Full submission text is pre-written: **`docs/SUBMISSION_DEVNETWORK.md`** — copy-paste ready.

### Step 5: Kite AI submission (Encode Club portal)

Full submission text is pre-written: **`docs/SUBMISSION_KITEAI.md`** — copy-paste ready.

The Kite AI submission emphasizes agent-native architecture and the N×B>M production formula, which aligns with Kite's focus.

---

## P1 — Nice to Have (May 17)

### Step 6: Demo video

Script is pre-written: **`docs/DEMO_VIDEO_SCRIPT.md`**

Quick version (30 minutes to record):
```bash
# Terminal 1: start recording
asciinema rec demo.cast

# Terminal 2: run the demo
cd ~/Desktop/hackathon/swarm-oracle
python swarm_verify.py --demo "Did BTC close above 100K on May 5, 2026?"
python swarm_verify.py --demo "Will the Fed cut rates 3+ times in 2026?"
make benchmark
make adversarial-compare
make economic-model-mvp

# Stop recording: Ctrl+D
asciinema upload demo.cast
```

Or use the existing YouTube link if already recorded: https://youtu.be/Dy1h0Hcr4HQ

### Step 7: Deploy contracts to Base Sepolia (if not already done)

```bash
# Get Base Sepolia ETH from faucet first:
# https://www.alchemy.com/faucets/base-sepolia
# https://faucet.quicknode.com/base/sepolia

# Then deploy:
cd ~/Desktop/hackathon/swarm-oracle/contracts
forge script script/Deploy.s.sol \
  --rpc-url $BASE_SEPOLIA_RPC \
  --private-key $PRIVATE_KEY \
  --broadcast \
  --verify
```

After deployment, update:
- `docs/DEPLOYMENT.md` — add contract addresses
- `README.md` — update contract addresses in the Contracts section
- DevPost submission — add Etherscan links

---

## What's Already Done (No Operator Action Needed)

| Item | Status | Location |
|------|--------|----------|
| CalibrationRegistry.sol | ✅ Complete | `contracts/src/` |
| SwarmConsensus.sol | ✅ Complete | `contracts/src/` |
| RewardDistribution.sol | ✅ Complete | `contracts/src/` |
| AgentIdentity.sol (soulbound ERC-721) | ✅ Complete | `contracts/src/` |
| Deploy.s.sol | ✅ Complete | `contracts/script/` |
| 55 Foundry tests (4 contracts) | ✅ Complete | `contracts/test/` |
| 742 Python tests (incl. test_submission_readiness.py, test_api.py) | ✅ Complete, 0 failures | `tests/` |
| Submission readiness test (verifies all 24 items) | ✅ Complete | `tests/test_submission_readiness.py` |
| 14 Python↔Solidity parity tests | ✅ Complete | `contracts/test/` |
| 90 adversarial tests | ✅ Complete | `tests/test_adversarial*.py` |
| 50 economic model tests | ✅ Complete | `tests/test_economic_model.py` |
| 83 Sybil resistance tests | ✅ Complete | `tests/test_sybil.py` |
| 34 Jupyter notebook tests | ✅ Complete | `tests/test_notebook.py` |
| Python↔contract bridge (bridge.py) | ✅ Complete | `contracts/bridge.py` |
| Reproducible benchmark (50-case, seed=42) | ✅ Complete | `scripts/benchmark.py` |
| Economic security model (N×B>M) | ✅ Complete | `scripts/economic_model.py` |
| 6-job CI pipeline | ✅ Complete | `.github/workflows/ci.yml` |
| GitHub Pages landing page | ✅ Complete | `index.html` |
| Interactive Jupyter notebook (22 cells) | ✅ Complete | `notebooks/swarm_oracle_demo.ipynb` |
| Threat model (formal adversarial) | ✅ Complete | `docs/threat-model.md` |
| Economic security doc | ✅ Complete | `docs/ECONOMIC_MODEL.md` |
| Competitive comparison | ✅ Complete | `docs/competitive-comparison.md` |
| DevNetwork submission text | ✅ Complete | `docs/SUBMISSION_DEVNETWORK.md` |
| Kite AI submission text | ✅ Complete | `docs/SUBMISSION_KITEAI.md` |
| Demo video script | ✅ Complete | `docs/DEMO_VIDEO_SCRIPT.md` |
| Docker compose | ✅ Complete | `docker-compose.yml` |
| JUDGES.md | ✅ Complete | `JUDGES.md` |
| README.md | ✅ Complete | `README.md` |

---

## Benchmark Numbers to Use in Submissions

| Method | Accuracy | Brier ↓ |
|--------|:--------:|:-------:|
| **swarm** | **100%** | **0.0724** |
| majority vote | 92.0% | 0.0785 |
| average | 98.0% | 0.0935 |
| agent-oracle | 84.0% | 0.1029 |

**Headline:** "Swarm Oracle achieves 100% accuracy and 0.0724 Brier on a 50-case deterministic benchmark, beating every single agent. 797 tests (742 Python + 55 Foundry), 0 failures. Zero external dependencies."

---

## Key URLs

| What | URL |
|------|-----|
| GitHub repo | https://github.com/SolMonger/swarm-oracle |
| Live landing page | https://solmonger.github.io/swarm-oracle/ |
| Demo video | https://youtu.be/Dy1h0Hcr4HQ |
| DevPost submission | https://devpost.com/software/swarm-oracle |
| Interactive notebook | `notebooks/swarm_oracle_demo.ipynb` (browser-renderable on GitHub) |
