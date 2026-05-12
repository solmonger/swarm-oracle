"""Evidence adapter — turn external research into Swarm Oracle Evidence records.

Two responsibilities:

1. **Adapt** the existing `forecast_lab/web_resolver.ResolutionResult` shape into
   a list of `consensus.Evidence` records, plus a probability estimate. This
   lets the existing battle-tested resolver feed directly into the swarm.

2. **Provide** lightweight free research functions for the demo:
     - `duckduckgo_search` — HTML scrape, no API key
     - `coingecko_price_evidence` — public crypto price API, no key

These are the "different research strategies" the design doc promises: web
search vs. structured API. Keeping both paths first-class lets us show that
the consensus engine handles diverse evidence sources without privileging any
one.

No paid APIs. No keys. Local-first, per the cost directive.
"""
from __future__ import annotations

import json
import logging
import re
import urllib.parse
import urllib.request
from typing import Any

from .consensus import Evidence

log = logging.getLogger("swarm_oracle.evidence")

USER_AGENT = "swarm-oracle/0.1 (contact: hackathon)"


# ---------------------------------------------------------------------------
# HTTP helpers — kept tiny so monkeypatching for tests is one line
# ---------------------------------------------------------------------------


def _fetch_html(url: str, headers: dict | None = None, timeout: float = 10) -> str:
    req = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, **(headers or {})}
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
        return r.read().decode("utf-8", errors="replace")


def _fetch_json(url: str, headers: dict | None = None, timeout: float = 10) -> Any:
    req = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, **(headers or {})}
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
        return json.loads(r.read())


# ---------------------------------------------------------------------------
# Adapter: forecast_lab.web_resolver.ResolutionResult → Evidence
# ---------------------------------------------------------------------------


def resolution_to_evidence(rr: Any) -> list[Evidence]:
    """Convert a `forecast_lab.web_resolver.ResolutionResult` to Evidence list.

    Returns [] if the resolution had no outcome (unresolvable). Otherwise
    returns a single Evidence record summarizing what the resolver found.
    """
    outcome = getattr(rr, "outcome", None)
    if outcome is None:
        return []

    source = getattr(rr, "source_url", None) or f"search:{getattr(rr, 'search_query', '')}"
    snippet = getattr(rr, "evidence", "") or ""
    confidence = float(getattr(rr, "confidence", 0.0))

    return [
        Evidence(
            source=source,
            snippet=snippet,
            timestamp=None,
            source_type="web_resolver",
            confidence=confidence,
        )
    ]


def probability_from_outcome(outcome: str, confidence: float) -> float:
    """Translate a resolver outcome ("yes" / "no" / "void") into a probability.

    Confidence interpolates between 0.5 (uncertain) and 1.0/0.0 (certain).

        yes  → 0.5 + 0.5 * confidence
        no   → 0.5 - 0.5 * confidence
        void → 0.5 (neutral)
    """
    confidence = max(0.0, min(1.0, float(confidence)))
    if outcome == "yes":
        return 0.5 + 0.5 * confidence
    if outcome == "no":
        return 0.5 - 0.5 * confidence
    return 0.5


# ---------------------------------------------------------------------------
# Strategy 1: DuckDuckGo HTML search (free, no API key)
# ---------------------------------------------------------------------------


def duckduckgo_search(query: str) -> str:
    """Search DuckDuckGo's HTML endpoint and return the raw text result.

    Designed to slot in as the `search_fn` callback that
    `forecast_lab.web_resolver.resolve_forecast_via_web` expects.
    """
    encoded = urllib.parse.quote(query)
    url = f"https://html.duckduckgo.com/html/?q={encoded}"
    try:
        html = _fetch_html(url, timeout=10)
    except Exception as exc:  # noqa: BLE001
        log.warning("duckduckgo_search failed for %r: %s", query, exc)
        return ""
    # Strip tags so the regex extractors in web_resolver work cleanly.
    return _strip_html(html)


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t]+")


def _strip_html(html: str) -> str:
    text = _TAG_RE.sub(" ", html)
    text = _WS_RE.sub(" ", text)
    # Preserve paragraph-ish line breaks — web_resolver splits on them.
    text = re.sub(r"\s*\n\s*", "\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Strategy 2: CoinGecko (free public API, no key)
# ---------------------------------------------------------------------------


_COINGECKO_ALIASES = {
    "btc": "bitcoin",
    "bitcoin": "bitcoin",
    "eth": "ethereum",
    "ethereum": "ethereum",
    "sol": "solana",
    "solana": "solana",
    "doge": "dogecoin",
    "dogecoin": "dogecoin",
}


def coingecko_price_evidence(asset: str, date: str | None = None) -> Evidence | None:
    """Fetch a price for `asset` from CoinGecko.

    `date` accepts dd-mm-yyyy (CoinGecko's required format for /history) OR
    None for current price. Returns None if the asset is unknown or the
    response is missing the expected fields.
    """
    coin_id = _COINGECKO_ALIASES.get(asset.lower(), asset.lower())

    if date:
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/history?date={date}"
    else:
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}"

    try:
        data = _fetch_json(url, timeout=10)
    except Exception as exc:  # noqa: BLE001
        log.warning("coingecko_price_evidence failed for %s: %s", asset, exc)
        return None

    if not isinstance(data, dict) or not data:
        return None

    market_data = data.get("market_data") or {}
    current = (market_data.get("current_price") or {}).get("usd")
    if current is None:
        return None

    snippet = (
        f"CoinGecko {coin_id}"
        + (f" on {date}" if date else " (current)")
        + f": ${current:,.2f} USD"
    )
    return Evidence(
        source=f"https://api.coingecko.com/api/v3/coins/{coin_id}",
        snippet=snippet,
        timestamp=date,
        source_type="api",
        confidence=0.95,  # Direct API quote — high trust
    )


def coingecko_price_usd(asset: str, date: str | None = None) -> float | None:
    """Convenience: just the price as a float, or None."""
    ev = coingecko_price_evidence(asset, date)
    if ev is None:
        return None
    m = re.search(r"\$([\d,]+\.\d{2})", ev.snippet)
    if not m:
        return None
    return float(m.group(1).replace(",", ""))
