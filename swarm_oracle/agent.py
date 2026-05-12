"""SwarmAgent — one verification agent.

Each agent has:

    - A unique `agent_id` (mapped to a calibration-history entry off-chain).
    - A `system_prompt` that nudges its perspective (skeptic, optimist, etc.).
    - A `research_strategy` name (and matching `research_fn`) that gathers
      evidence — e.g. "web_search", "api", "knowledge".
    - A `llm_call` callable that takes a prompt and returns the raw model text.

The default LLM call hits a local OpenAI-compatible server (set LLM_API_URL). All defaults can be overridden
for tests, ablations, or post-hackathon experimentation.

`default_swarm()` constructs a 3-agent fleet that uses two distinct research
strategies (web search + API + knowledge), satisfying the Week 1 DoD.
"""
from __future__ import annotations

import json
import os
import logging
import re
import urllib.request
from dataclasses import dataclass, field
from typing import Callable

from .consensus import AgentVote, Evidence
from .evidence import coingecko_price_evidence, duckduckgo_search

log = logging.getLogger("swarm_oracle.agent")

LLAMA_URL = os.environ.get("LLM_API_URL", "http://127.0.0.1:8080/v1/chat/completions")
LLAMA_MODEL = os.environ.get("LLM_MODEL", "default")  # model name sent to the server
LLAMA_TIMEOUT = 90  # seconds per call


# ---------------------------------------------------------------------------
# Default LLM call (Gemma4 on :8090) and JSON parser
# ---------------------------------------------------------------------------


def default_llm_call(prompt: str, *, temperature: float = 0.3) -> str:
    """Call the local llama.cpp Gemma4 server. Returns raw model text."""
    payload = {
        "model": LLAMA_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": 512,
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        LLAMA_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=LLAMA_TIMEOUT) as r:  # noqa: S310
        resp = json.loads(r.read())
    return resp["choices"][0]["message"]["content"]


def _parse_json(raw: str) -> dict | None:
    """Strip markdown fences and parse JSON. Returns None on failure."""
    text = raw.strip()
    if text.startswith("```"):
        nl = text.find("\n")
        if nl != -1:
            text = text[nl + 1 :]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3].rstrip()
    lines = text.splitlines()
    if lines and lines[0].strip().lower() == "json":
        text = "\n".join(lines[1:]).strip()

    # Try strict parse first.
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    # Fallback: find the first {...} blob.
    m = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    return None


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(x)))


# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------


PROMPT_TEMPLATE = """{system_prompt}

You will assess whether a real-world claim is TRUE based on the evidence below.
Output ONLY a JSON object — no preamble, no commentary.

JSON schema (all fields required):
{{
  "probability": <float in [0.0, 1.0], your P(claim is true)>,
  "confidence":  <float in [0.0, 1.0], your meta-confidence in that estimate>,
  "reasoning":   "<one or two sentences citing the evidence>"
}}

Decision guidance:
- If the evidence directly confirms the claim, probability should be ≥ 0.9.
- If the evidence directly refutes it, probability should be ≤ 0.1.
- If evidence is mixed or absent, stay near 0.5 with low confidence.
- Never invent evidence. If you do not know, say so via low confidence.

Claim to verify:
{question}

Evidence:
{evidence_block}

Respond with ONLY the JSON object."""


def _format_evidence(evs: list[Evidence]) -> str:
    if not evs:
        return "(no evidence collected — answer from prior knowledge with low confidence)"
    lines = []
    for i, e in enumerate(evs, 1):
        ts = f" ({e.timestamp})" if e.timestamp else ""
        lines.append(
            f"{i}. [{e.source_type}] {e.source}{ts} (confidence={e.confidence:.2f})\n"
            f"   {e.snippet[:500]}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# SwarmAgent
# ---------------------------------------------------------------------------


@dataclass
class SwarmAgent:
    agent_id: str
    system_prompt: str
    research_strategy: str
    llm_call: Callable[..., str] = field(default=default_llm_call)
    research_fn: Callable[[str], list[Evidence]] = field(
        default_factory=lambda: (lambda q: [])
    )
    temperature: float = 0.3

    def verify(self, question: str) -> AgentVote:
        evidence = self._collect_evidence(question)
        prompt = PROMPT_TEMPLATE.format(
            system_prompt=self.system_prompt,
            question=question,
            evidence_block=_format_evidence(evidence),
        )

        try:
            raw = self.llm_call(prompt, temperature=self.temperature)
        except Exception as exc:  # noqa: BLE001
            log.warning("agent %s LLM call failed: %s", self.agent_id, exc)
            return self._neutral_vote(evidence, reason=f"LLM call failed: {exc}")

        parsed = _parse_json(raw)
        if parsed is None:
            log.warning(
                "agent %s produced unparseable output: %r",
                self.agent_id,
                raw[:200],
            )
            return self._neutral_vote(
                evidence, reason=f"unparseable model output: {raw[:80]}"
            )

        try:
            probability = _clamp(float(parsed.get("probability", 0.5)))
            confidence = _clamp(float(parsed.get("confidence", 0.3)))
        except (TypeError, ValueError):
            return self._neutral_vote(evidence, reason="malformed numeric fields")

        reasoning = str(parsed.get("reasoning", "")).strip() or "(no reasoning given)"

        return AgentVote(
            agent_id=self.agent_id,
            probability=probability,
            confidence=confidence,
            evidence=evidence,
            reasoning=reasoning,
            research_strategy=self.research_strategy,
        )

    def _collect_evidence(self, question: str) -> list[Evidence]:
        try:
            return list(self.research_fn(question) or [])
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "agent %s research_fn failed: %s",
                self.agent_id,
                exc,
            )
            return []

    def _neutral_vote(self, evidence: list[Evidence], reason: str) -> AgentVote:
        return AgentVote(
            agent_id=self.agent_id,
            probability=0.5,
            confidence=0.1,
            evidence=evidence,
            reasoning=f"NEUTRAL ({reason})",
            research_strategy=self.research_strategy,
        )


# ---------------------------------------------------------------------------
# Research strategy implementations
# ---------------------------------------------------------------------------


def web_search_research(question: str) -> list[Evidence]:
    """DuckDuckGo HTML scrape — generic web research strategy."""
    text = duckduckgo_search(question)
    if not text:
        return []
    # Take the first ~600 chars as a rough snippet of the SERP.
    snippet = text[:600]
    return [
        Evidence(
            source=f"search:{question}",
            snippet=snippet,
            timestamp=None,
            source_type="web",
            confidence=0.6,
        )
    ]


_BTC_PATTERNS = [
    r"\b(bitcoin|btc)\b",
    r"\b(ethereum|eth)\b",
    r"\b(solana|sol)\b",
    r"\b(dogecoin|doge)\b",
]
_DATE_PATTERN = re.compile(
    r"\b(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})\b"  # dd-mm-yyyy or m/d/yy
)


def crypto_api_research(question: str) -> list[Evidence]:
    """CoinGecko API — when the question mentions a known crypto asset.

    Returns an empty list if no asset is detected, so the consensus engine
    still has a vote (at neutral) without us inventing facts.
    """
    q_low = question.lower()
    asset = None
    for pat in _BTC_PATTERNS:
        m = re.search(pat, q_low)
        if m:
            asset = m.group(0).lower()
            break
    if asset is None:
        return []

    # Try to extract a date — CoinGecko wants dd-mm-yyyy.
    date = _extract_date_for_coingecko(question)

    ev = coingecko_price_evidence(asset, date)
    return [ev] if ev else []


def _extract_date_for_coingecko(question: str) -> str | None:
    # Prefer ISO-style dates (yyyy-mm-dd) if present.
    iso = re.search(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b", question)
    if iso:
        y, m, d = iso.groups()
        return f"{int(d):02d}-{int(m):02d}-{y}"
    # "May 5, 2026" → 05-05-2026 (CoinGecko format)
    months = {
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12,
    }
    m = re.search(
        r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(\d{1,2}),?\s+(20\d{2})\b",
        question,
        re.IGNORECASE,
    )
    if m:
        mon_str = m.group(1).lower()
        mon_full = next((k for k in months if k.startswith(mon_str)), None)
        if mon_full:
            return f"{int(m.group(2)):02d}-{months[mon_full]:02d}-{m.group(3)}"
    return None


def knowledge_only_research(question: str) -> list[Evidence]:
    """No external research — agent reasons from its own training."""
    return []


# ---------------------------------------------------------------------------
# Default 3-agent swarm (Week 1 demo)
# ---------------------------------------------------------------------------


def default_swarm() -> list[SwarmAgent]:
    """Construct a 3-agent fleet with diverse prompts + research strategies.

    - agent-oracle:  highest-calibration tier, uses crypto API for finance
                     questions (high signal-to-noise on prices).
    - agent-reliable: mid tier, uses general web search.
    - agent-novice:  no-tools, knowledge-only — sanity check the LLM is
                     anchored to evidence rather than its priors.
    """
    return [
        SwarmAgent(
            agent_id="agent-oracle",
            system_prompt=(
                "You are agent-oracle, a methodical financial verifier. "
                "Trust direct API quotes over hearsay. Think before you answer."
            ),
            research_strategy="api",
            research_fn=crypto_api_research,
            temperature=0.2,
        ),
        SwarmAgent(
            agent_id="agent-reliable",
            system_prompt=(
                "You are agent-reliable, a general-purpose researcher. "
                "Cross-reference web sources before committing to an answer."
            ),
            research_strategy="web_search",
            research_fn=web_search_research,
            temperature=0.4,
        ),
        SwarmAgent(
            agent_id="agent-novice",
            system_prompt=(
                "You are agent-novice. You have no live tools — answer from "
                "general knowledge. Stay near 0.5 probability if uncertain."
            ),
            research_strategy="knowledge",
            research_fn=knowledge_only_research,
            temperature=0.6,
        ),
    ]
