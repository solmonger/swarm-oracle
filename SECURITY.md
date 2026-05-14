# Security Policy

## Reporting a vulnerability

Please **do not file public GitHub issues** for security vulnerabilities.
The repo is under active hackathon submission and a public report could be
exploited before we have time to patch.

Instead, email **eshaan.mathakari@gmail.com** with:

1. A short description of the issue
2. Reproduction steps, including affected commit SHA
3. Your assessment of severity (informational / low / medium / high /
   critical)
4. Whether you'd like to be credited in the patch notes

We aim to acknowledge reports within 48 hours and ship a fix within 7 days
for high-severity issues. For lower-severity findings, we'll coordinate a
disclosure timeline that gives downstream integrators time to update.

## Scope

The following are in-scope for a security report:

- **Consensus correctness.** Any input that causes
  `swarm_oracle.consensus.aggregate_consensus` to return a decision that
  violates the protocol semantics in `design.md` and the test suite.
- **Calibration-registry integrity.** Any way to inflate or deflate an
  agent's calibration weight without making real predictions.
- **Sybil attacks below the cost documented in `docs/security-model.md`.**
  If you can flip the canonical demo scenario for fewer than 272
  base-weight Sybils (or otherwise beat the analysis we publish), please
  let us know — that's the most valuable kind of finding.
- **On-chain contracts.** The four contracts in `contracts/` are early-
  stage and not yet audited. Reentrancy, integer over/underflow, access-
  control bypass, MEV-exploitable orderings, gas griefing, or any
  divergence from the Python reference implementation are all in scope.
- **API surface.** The FastAPI service in `swarm_oracle/api.py` accepts
  user input and returns oracle decisions. Injection, denial-of-service,
  or response-spoofing issues are in scope.
- **Build supply chain.** The two GitHub Actions workflows
  (`.github/workflows/ci.yml`, `.github/workflows/pages.yml`) pin major
  action versions but not commit SHAs. If you find a way for a malicious
  action update to compromise the deployment pipeline, that's in scope.

The following are explicitly **out of scope** for a vulnerability report
(but are still welcome as regular issues / PRs):

- The vault directory referenced in `CLAUDE.md` (it's a local-only design
  ledger, not deployed code).
- Performance issues that are not also correctness issues.
- Style / readability concerns.
- Disagreements with documented protocol design choices (e.g.
  `DEFAULT_VARIANCE_THRESHOLD = 0.20`). These are tunable; open an issue
  proposing a different value and we'll discuss.

## What you'll get back

For valid in-scope reports we will:

1. Acknowledge receipt within 48 hours.
2. Confirm the issue (or explain why we believe it's out of scope) within
   7 days.
3. Patch the issue and ship a fix on `main`.
4. Credit you in the commit message and (with permission) in the project
   README, unless you prefer to remain anonymous.

This project is pre-revenue. We don't have a paid bug-bounty program. We
do have deep appreciation, public credit, and a commitment to handle your
report with respect for the time you put into it.

## Cryptographic / blockchain-specific guidance

The on-chain contracts target Base Sepolia (testnet) and are not yet
deployed to mainnet. If you find an issue that would be exploitable on
mainnet:

- Please **do not** test it against any live deployment without explicit
  written permission. Base Sepolia testnet is fair game; mainnet
  contracts (when they exist) require coordination.
- Report the issue privately even if no funds are at risk — we want to
  ship a hardened mainnet contract, and your finding is valuable
  regardless of current TVL.

## Disclosure history

No security disclosures yet. This document will be updated when one
occurs. Suggested format for future entries:

```
## YYYY-MM-DD — <short title>
**Severity:** medium
**Reporter:** <name or "anonymous">
**Summary:** One-paragraph description.
**Patch:** Commit <SHA>, released in version <X.Y.Z>.
```
