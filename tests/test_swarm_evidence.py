"""Tests for swarm_oracle.evidence — adapter from forecast_lab web_resolver to Evidence."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from swarm_oracle import evidence as E  # noqa: E402
from swarm_oracle.consensus import Evidence  # noqa: E402


def _has_forecast_lab() -> bool:
    try:
        import forecast_lab  # noqa: F401
        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# resolution_to_evidence — adapter from web_resolver.ResolutionResult
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not _has_forecast_lab(),
    reason="forecast_lab not available (openclaw-infra internal)",
)
def test_resolution_to_evidence_preserves_outcome_and_confidence():
    """A web-resolution result with outcome + confidence becomes one Evidence record."""
    from forecast_lab.web_resolver import ResolutionResult

    rr = ResolutionResult(
        forecast_id="f-test",
        outcome="yes",
        confidence=0.91,
        evidence="BTC price found: $103,500 vs threshold $100,000 (above)",
        search_query="BTC price 2026-05-05",
        source_url="https://www.coingecko.com/coins/bitcoin",
    )
    out = E.resolution_to_evidence(rr)
    assert isinstance(out, list)
    assert len(out) == 1
    ev = out[0]
    assert isinstance(ev, Evidence)
    assert ev.confidence == pytest.approx(0.91)
    assert "BTC" in ev.snippet or "103,500" in ev.snippet
    assert ev.source == "https://www.coingecko.com/coins/bitcoin"


@pytest.mark.skipif(
    not _has_forecast_lab(),
    reason="forecast_lab not available (openclaw-infra internal)",
)
def test_resolution_to_evidence_with_no_url_uses_search_query_as_source():
    from forecast_lab.web_resolver import ResolutionResult

    rr = ResolutionResult(
        forecast_id="f",
        outcome="no",
        confidence=0.6,
        evidence="some text",
        search_query="my query",
        source_url=None,
    )
    out = E.resolution_to_evidence(rr)
    assert out[0].source == "search:my query"


@pytest.mark.skipif(
    not _has_forecast_lab(),
    reason="forecast_lab not available (openclaw-infra internal)",
)
def test_resolution_to_evidence_returns_empty_when_no_outcome():
    """Unresolvable results produce no evidence."""
    from forecast_lab.web_resolver import ResolutionResult

    rr = ResolutionResult(
        forecast_id="f",
        outcome=None,
        confidence=0.0,
        evidence="could not parse",
        search_query="q",
        source_url=None,
    )
    assert E.resolution_to_evidence(rr) == []


# ---------------------------------------------------------------------------
# probability_from_outcome — translate yes/no into a probability
# ---------------------------------------------------------------------------


def test_probability_from_outcome_yes_high_confidence():
    p = E.probability_from_outcome("yes", confidence=0.9)
    # A "yes" with 0.9 confidence should be 0.95 (halfway between 0.5 and 1.0
    # by confidence) or similar — the only invariant we lock in is direction.
    assert p > 0.5
    assert p <= 1.0


def test_probability_from_outcome_no_high_confidence():
    p = E.probability_from_outcome("no", confidence=0.9)
    assert p < 0.5
    assert p >= 0.0


def test_probability_from_outcome_low_confidence_near_neutral():
    p_yes = E.probability_from_outcome("yes", confidence=0.0)
    assert p_yes == pytest.approx(0.5)


def test_probability_from_outcome_void_returns_neutral():
    p = E.probability_from_outcome("void", confidence=0.9)
    assert p == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Sources — DuckDuckGo HTML, CoinGecko
# ---------------------------------------------------------------------------


def test_duckduckgo_search_function_uses_callable(monkeypatch):
    """duckduckgo_search returns a callable that fetches HTML and returns text."""
    captured: dict[str, str] = {}

    def fake_fetch(url: str, headers: dict | None = None, timeout: float = 10) -> str:
        captured["url"] = url
        return "<html>BTC price is $103,500 today</html>"

    monkeypatch.setattr(E, "_fetch_html", fake_fetch)
    fn = E.duckduckgo_search
    text = fn("BTC price 2026-05-05")
    assert "url" in captured
    assert "duckduckgo" in captured["url"]
    assert "103,500" in text


def test_coingecko_price_fetch_returns_evidence(monkeypatch):
    def fake_json(url: str, headers: dict | None = None, timeout: float = 10) -> dict:
        # CoinGecko historical endpoint
        return {
            "id": "bitcoin",
            "symbol": "btc",
            "market_data": {
                "current_price": {"usd": 103500.0},
            },
        }

    monkeypatch.setattr(E, "_fetch_json", fake_json)
    ev = E.coingecko_price_evidence(asset="bitcoin", date="05-05-2026")
    assert ev is not None
    assert isinstance(ev, Evidence)
    assert "103500" in ev.snippet or "103,500" in ev.snippet
    assert ev.source_type == "api"
    assert "coingecko" in ev.source.lower()


def test_coingecko_unknown_asset_returns_none(monkeypatch):
    def fake_json(url: str, headers: dict | None = None, timeout: float = 10) -> dict:
        # CoinGecko returns {} for unknown coin
        return {}

    monkeypatch.setattr(E, "_fetch_json", fake_json)
    ev = E.coingecko_price_evidence(asset="not-a-real-coin", date="05-05-2026")
    assert ev is None
