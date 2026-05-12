# Swarm Oracle — Demo Video Script

**Target length:** 4–5 minutes  
**Format:** Screen recording with voiceover  
**Tools needed:** Terminal, browser (for demo.html + basescan)

---

## Scene 1: Hook (0:00–0:30)

**[Show terminal with Swarm Oracle banner]**

> "What if you could ask an AI a yes-or-no question — and instead of trusting one model's answer, you got a calibration-weighted consensus from multiple agents, each with a verified track record?"
>
> "That's Swarm Oracle. Agents that are more accurate get more influence. And the math is verifiable on-chain."

---

## Scene 2: The Problem (0:30–1:00)

**[Show a simple slide or text overlay]**

> "Single-model prediction has a fundamental problem: you don't know how much to trust the answer. Different models are better at different domains. Some are overconfident. Some hedge everything."
>
> "Prediction markets solve this with money — but that locks out most agents and most questions."
>
> "Swarm Oracle solves it with math: Brier scores measure calibration. Better-calibrated agents earn more weight. No stake required."

---

## Scene 3: Live Demo — CLI (1:00–2:30)

**[Terminal, run demo mode]**

```bash
python swarm_verify.py --demo "Did BTC close above $100K on May 5, 2026?"
```

> "Here's a crypto question. Three agents research it independently — one uses a price API, one searches the web, one relies on knowledge alone."
>
> "Look at the weights: agent-oracle has a Brier score of 0.08 across 220 predictions — it gets 60% of the vote. The novice agent with no track record? Only 6%."
>
> "The consensus probability is 0.065 — a confident NO. And notice the variance is low, meaning the well-calibrated agents agree."

**[Run a second question]**

```bash
python swarm_verify.py --demo "Will Barcelona win the match against Alaves?"
```

> "Same system, different domain. The weights automatically adapt because each agent's Brier score reflects their actual accuracy history."

**[Show JSON output]**

```bash
python swarm_verify.py --demo --json "Will it rain in Zurich tomorrow?" | python3 -m json.tool | head -25
```

> "Machine-readable output for downstream integrations."

---

## Scene 4: Interactive Dashboard (2:30–3:15)

**[Open demo.html in browser]**

> "For the visual thinkers — here's the interactive demo. Pick a question, watch the agents research in real-time, see the calibration weights visualized."
>
> "The bar chart shows each agent's weight share. The consensus gauge shows the final probability. And if agents disagree strongly, you get a DISPUTE — not a misleading average."

---

## Scene 5: On-Chain Verification (3:15–4:00)

**[Show basescan with deployed contracts]**

> "Everything is verifiable on Base Sepolia. Four contracts:"
>
> "CalibrationRegistry stores each agent's Brier score and computes weights using 18-decimal fixed-point math — the same formula as the Python engine, bit-for-bit."
>
> "SwarmConsensus reads those weights, accepts vote submissions, and resolves YES, NO, or DISPUTE."
>
> "RewardDistribution splits ETH reward pools — 70% by calibration weight, 30% accuracy bonus."
>
> "AgentIdentity issues soulbound NFTs — non-transferable reputation tokens."

**[Show bridge.py parity test output or reference it]**

> "We have 14 parity tests that verify the Python math matches the Solidity math exactly. Off-chain speed, on-chain trust."

---

## Scene 6: The Flywheel (4:00–4:30)

**[Show architecture diagram or text overlay]**

> "Here's what makes this different: it's a self-improving system."
>
> "Every resolved question updates the Brier scores. Better scores mean more weight. More weight means better consensus. And the resolution data feeds back into DPO fine-tuning of the agents themselves."
>
> "We didn't just build an oracle. We built a system that gets more accurate every time it's used."

---

## Scene 7: Close (4:30–5:00)

**[Terminal with test results]**

```bash
python3 -m pytest tests/ --tb=short -q
```

> "108 Python tests. Full Foundry test suite. Zero external dependencies. Runs on consumer hardware with any local LLM."
>
> "Swarm Oracle — calibration-weighted consensus where accuracy is earned, not bought."
>
> "MIT licensed. GitHub link in the description."

---

## Recording Checklist

- [ ] Clean terminal (dark theme, large font)
- [ ] Demo mode works without LLM server (`--demo` flag)
- [ ] demo.html opens correctly in browser
- [ ] Base Sepolia contracts visible on basescan
- [ ] Test suite passes cleanly
- [ ] Record at 1920x1080 or 2560x1440
- [ ] Voiceover recorded separately for clean audio
