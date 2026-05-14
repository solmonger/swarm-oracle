# Swarm Oracle vs Existing Oracles — Competitive Comparison

**Audience:** Hackathon judges, protocol researchers, integrators
deciding whether to use Swarm Oracle for a new prediction market or
on-chain data feed.

**Scope:** Pairwise comparison against the five most-cited oracle
architectures in production today: **UMA**, **Augur v2**, **Reality.eth**
(Kleros backstop), **Chainlink Price Feeds**, and **Pyth Network**.

The goal is not to claim universal superiority — every oracle exists
for a reason. The goal is to **position Swarm Oracle** by drawing
explicit comparisons on the dimensions that matter for AI-resolvable
prediction markets.

---

## TL;DR matrix

| Dimension | UMA | Augur v2 | Reality.eth | Chainlink | Pyth | **Swarm Oracle** |
|---|---|---|---|---|---|---|
| Trust model | Optimistic + token-stake disputes | REP-token reporters + dispute rounds | Token bond + Kleros jury | Whitelisted node operators | Validated publishers + price aggregation | **Calibration-weighted AI swarm** |
| Settlement time (uncontested) | 2 h liveness window | Several hours | ~24 h on-chain bond window | < 30 s per round | < 1 s | **~3 s for AI-resolvable claims** |
| Settlement time (contested) | 48+ h | 7+ days (rounds) | Weeks via Kleros | n/a (no dispute layer) | n/a | **~3 s** (re-runs are protocol-internal) |
| Self-improving accuracy | No | No | No | No | No | **Yes** (DPO loop over resolved markets) |
| Question types | Anything humans can verify | Anything humans can verify | Anything humans can verify | Price / numeric feeds only | Price / market data | **Anything an LLM with web search can verify** |
| Capital required to attack | $1M+ UMA stake | $10M+ REP stake | Bond + Kleros voting cost | Compromise validator set | Compromise publishers | **~$500 (3-agent demo) to ~$10k+ (production swarm)** at bribery; **~$1.3k** at Sybil |
| Per-resolution cost | $5–$50 on Ethereum L1 | $5–$50 on Ethereum L1 | $5–$50 on Ethereum L1 | Bundled with feed price | Bundled with feed price | **~$0.30** on Base Sepolia for the on-chain commit |
| Public open-source code | [yes](https://github.com/UMAprotocol/protocol) | [yes](https://github.com/AugurProject/augur) | [yes](https://github.com/RealityETH/reality-eth-monorepo) | [yes](https://github.com/smartcontractkit/chainlink) | [yes](https://github.com/pyth-network/pyth-client) | **yes** (this repo) |
| LLM-native | No | No | No | No | No | **Yes** — built around verifiable LLM votes |

---

## §1. UMA (Optimistic Oracle)

**Architecture.** A submitter posts a proposed resolution + bond. If no
one disputes within a 2-hour liveness window, the resolution is final.
A dispute triggers a UMA token-holder vote with a 48-hour commit-reveal
schedule.

**Strengths.** Battle-tested on Polymarket, billions in TVL resolved.
Game-theoretic security: a successful attack requires more value than
the UMA token's market cap.

**Weaknesses for prediction markets.**

* **Cold-start latency.** Even uncontested resolutions take ~2 hours
  — useless for markets that resolve and need to pay out the same day.
* **Disputes block resolution.** A single griefer with a small bond
  can delay resolution by 48 hours.
* **Human-resolver bottleneck.** The dispute round requires UMA
  token-holders to actively review the question. Many low-value
  markets never recruit enough disputers to pass the bond threshold.

**Why Swarm Oracle is different.** Resolution is computed by a swarm of
LLM agents that vote on the question's outcome with calibration-weighted
consensus. Resolution latency is **bound by inference time, not by
human review windows** — ~3 seconds in the demo. There's no "liveness
window" because the protocol does not assume any human submitter.
Disputes are *first-class* (the DISPUTE decision arm) but are
*synchronous*: a disputed market is flagged immediately and re-runs
with more agents, not deferred 48 hours.

**Numerical comparison.** UMA dispute resolution: 48 hours. Swarm
Oracle DISPUTE → re-run: ~3 seconds (see
[`benchmark.json`](../benchmark.json) for the headline 0.0859 Brier
score on the calibration eval).

---

## §2. Augur v2

**Architecture.** REP token holders report on market outcomes. Disputes
escalate through rounds; final disputes can fork the REP token. Markets
resolve over hours-to-days.

**Strengths.** Decentralized — anyone with REP can report. Strong
incentive alignment via fork threat.

**Weaknesses for prediction markets.**

* **Long settlement time** — multi-day in disputed cases.
* **Liquidity collapsed post-v1 due to UX and gas cost.**
* **Reporter capture** — a small set of REP whales dominates reporting.

**Why Swarm Oracle is different.** The dominant set isn't humans with
stake — it's the highest-calibrated AI agents on the calibration
registry. Calibration is *earned*, not bought, and the protocol's
weight ceiling for a constant-vote attacker ($\le 3.984$, per
`security-model.md` §3) prevents stake-based whale capture.

---

## §3. Reality.eth + Kleros

**Architecture.** Crowdsourced oracle: anyone can answer a question by
posting a bond. Disputes escalate to Kleros, a decentralized court
where token-staked jurors vote on the truthful answer.

**Strengths.** Mature, used by Omen and several DAOs. Kleros provides
appeals all the way up to a "general court."

**Weaknesses for prediction markets.**

* **Settlement is slow.** Bond windows run 6–24 hours; Kleros appeals
  add weeks.
* **Juror review quality is variable.** A juror has minutes to
  research and submit; calibration is not measured or rewarded.
* **Bribery surface is large.** Public juror identities + the appeals
  process make targeted bribery possible.

**Why Swarm Oracle is different.** Quality is *the protocol's quality
function* — the calibration registry tracks Brier scores per agent
forever, and the consensus formula deweights agents that have been
wrong before. Bribery cost per agent scales with the agent's expected
future earnings (see `threat-model.md` §3), not with a flat per-juror
fee.

---

## §4. Chainlink Price Feeds

**Architecture.** Whitelisted node operators report off-chain data on
a fixed schedule (or on-demand). Median of reports is the on-chain
value.

**Strengths.** The dominant oracle for DeFi. Sub-second latency for
hot feeds, $20B+ TVL secured.

**Weaknesses for prediction markets.**

* **Numeric feeds only.** Cannot resolve free-form questions like
  "Did Apple announce a foldable iPhone in Q3?" — only "what is the
  ETH/USD price right now?"
* **Whitelisted operators.** The node set is curated; permissionless
  participation is not the model.

**Why Swarm Oracle is different.** Different design space: Chainlink
optimizes for high-frequency numeric data with known publishers; Swarm
Oracle optimizes for arbitrary natural-language questions with
verifiable web evidence. **The two are complements, not competitors** —
a production prediction market could use Chainlink for "what was the
ETH price at block N" and Swarm Oracle for "did the SEC approve the
ETF?"

---

## §5. Pyth Network

**Architecture.** Publishers (exchanges, market makers) push prices
into a pull-based oracle layer that aggregates with a confidence-weighted
median. Sub-second freshness; pay-per-pull on Solana / EVM L2s.

**Strengths.** Lowest-latency oracle in production for price data.

**Weaknesses for prediction markets.** Same as Chainlink — price feeds
only, doesn't handle natural-language questions.

**Why Swarm Oracle is different.** Same complementary positioning as
§4. The Pyth confidence-weighted aggregation is conceptually similar
to Swarm Oracle's weight-aware variance gate, but Pyth weights are
based on publisher self-reported confidence, while Swarm Oracle
weights are based on **empirically measured Brier scores** — a stricter
signal because publishers can lie about confidence but cannot fake
historical calibration.

---

## §6. Comparison summary by attribute

### Settlement time

| Oracle | Uncontested | Disputed |
|---|---|---|
| Pyth | < 1 s | n/a |
| Chainlink | < 30 s | n/a |
| **Swarm Oracle** | **~3 s** | **~3 s (synchronous DISPUTE)** |
| UMA | 2 h | 48 h |
| Augur v2 | hours | days |
| Reality.eth | 6–24 h | weeks |

Swarm Oracle is the **only oracle in this set that resolves
free-form questions in seconds rather than hours.**

### Trust model

| Oracle | Trust anchor | What changes with scale |
|---|---|---|
| UMA | UMA token economic value | More stake → more security |
| Augur v2 | REP token + fork threat | More REP → more dispersion |
| Reality.eth | Kleros juror set | More jurors → more variance |
| Chainlink | Whitelisted operators | Add operators → harder MEV |
| Pyth | Whitelisted publishers | Add publishers → tighter median |
| **Swarm Oracle** | **Calibration history per agent** | **More agents + more resolved markets → harder bribery + harder Sybil** |

### Per-resolution cost (back of envelope)

| Oracle | Network | Typical cost |
|---|---|---|
| UMA on Ethereum L1 | $5–$50 (gas-dominated) |
| Augur v2 on Ethereum L1 | $5–$50 |
| Reality.eth on Ethereum L1 | $5–$50 |
| Chainlink Data Feeds | bundled (often free for consumers) |
| Pyth | per-pull, ~$0.10 |
| **Swarm Oracle on Base Sepolia** | **~$0.30** for the on-chain commit; off-chain inference ~free with local Gemma |

### Attack-cost basis (3-agent canonical demo)

Numbers from `python -m scripts.adversarial_demo --compare`:

| Attack vector | Cost |
|---|---|
| Sybil (272 base-weight registrations) | **$1,360** |
| Bribery (2 agents flipped) | **$500** |
| Cheapest | **bribery** |

Attack cost scales with swarm size. At 10 high-weight honest agents and
$c_b = \$2,000$: Sybil ~$1,360, bribery ~$10,000 — Sybil becomes
cheaper. See `threat-model.md` §4 for the crossover analysis.

### LLM-native

Of the six oracles compared, **only Swarm Oracle is built around LLM
votes from the ground up**. All others are either price-numeric or
human-juror; AI-native resolution is the protocol's core thesis.

---

## §7. Positioning statement

> Swarm Oracle is **not a replacement for Chainlink** — it complements
> price feeds with AI-native resolution of free-form questions.
>
> Swarm Oracle is **a replacement for UMA / Augur / Reality.eth** when
> the market needs to resolve in seconds rather than hours, when
> resolution quality is measurable (Brier score), and when the
> resolution surface is LLM-verifiable from public web evidence.

The 30-second hackathon pitch: *"Calibration-weighted AI swarms are
faster than human-jury oracles, more flexible than price feeds, and —
once a few resolutions are on-chain — self-improving."*

---

## §8. What we don't do (intellectual honesty)

* **Swarm Oracle is not appropriate for** questions where the
  resolution requires access to **private** data (e.g. internal
  company KPIs, non-public legal filings). LLMs without that access
  will produce low-confidence votes.
* **Swarm Oracle is not appropriate for** numeric price feeds where
  sub-second latency matters — Pyth/Chainlink dominate.
* **Swarm Oracle does not (yet) implement slashing**. A bribed
  agent's calibration weight drops on the next resolution, but the
  agent doesn't lose stake. This is on the v0.2 roadmap — see
  `RewardDistribution.sol` and `threat-model.md` §7.
* **Swarm Oracle's headline 91.7% accuracy / 0.0859 Brier** is on a
  curated 24-question eval (`benchmark.json`). Real-world deployment
  will see different distributions. The protocol is designed to *learn
  from* deployment data via the DPO loop; numbers will move with use.

---

## §9. References

* UMA: [docs.uma.xyz](https://docs.uma.xyz/), [Polymarket UMA
  integration](https://docs.polymarket.com/#how-are-markets-resolved)
* Augur v2: [augur.net](https://augur.net), [whitepaper](https://github.com/AugurProject/whitepaper)
* Reality.eth: [reality.eth](https://reality.eth.limo/),
  [Kleros general court](https://klerosboard.com/)
* Chainlink: [chain.link/docs](https://docs.chain.link/)
* Pyth: [pyth.network/docs](https://docs.pyth.network/)
* Swarm Oracle: [this repo](../README.md);
  [`security-model.md`](./security-model.md);
  [`threat-model.md`](./threat-model.md)

For exact code-level differences, run `make adversarial-compare` and
read `swarm_oracle/adversarial.py` alongside the linked competitor
documentation.
