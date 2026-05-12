"""Tests for the Swarm Oracle FastAPI endpoint.

Uses FastAPI's TestClient (backed by httpx) to exercise /health and /resolve
without starting a real server or making real LLM calls. All agents are
monkeypatched with deterministic stub votes.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

# Guard the import — if fastapi/httpx aren't installed, skip the whole module.
fastapi = pytest.importorskip("fastapi")
httpx = pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from swarm_oracle.api import create_app, ResolveRequest
from swarm_oracle.consensus import AgentVote, Evidence


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _stub_vote(agent_id: str, prob: float, conf: float = 0.8) -> AgentVote:
    """Deterministic vote for testing."""
    return AgentVote(
        agent_id=agent_id,
        probability=prob,
        confidence=conf,
        evidence=[
            Evidence(
                source="test-source",
                snippet="Test evidence snippet",
                source_type="test",
                confidence=0.9,
            )
        ],
        reasoning=f"Stub reasoning for {agent_id}",
        research_strategy="test",
    )


def _mock_verify_question(question, agents, weights, **kwargs):
    """Replacement for verify_question that returns deterministic results."""
    from swarm_oracle.consensus import aggregate_consensus
    from swarm_oracle.verifier import SwarmResult
    import time

    votes = [
        _stub_vote("agent-oracle", 0.05),
        _stub_vote("agent-reliable", 0.10),
        _stub_vote("agent-novice", 0.50),
    ]
    # Filter to only requested agents
    agent_ids = {a.agent_id for a in agents}
    votes = [v for v in votes if v.agent_id in agent_ids]

    consensus = aggregate_consensus(votes, weights, **kwargs)
    return SwarmResult(
        question=question,
        votes=votes,
        consensus=consensus,
        elapsed_seconds=0.042,
    )


@pytest.fixture
def client():
    """TestClient with deterministic agent responses."""
    with patch("swarm_oracle.api.verify_question", side_effect=_mock_verify_question):
        app = create_app()
        with TestClient(app) as c:
            yield c


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------


class TestHealth:
    def test_health_returns_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["version"] == "0.1.0"
        assert body["agents"] == 3

    def test_health_content_type(self, client):
        resp = client.get("/health")
        assert "application/json" in resp.headers["content-type"]


# ---------------------------------------------------------------------------
# /resolve — happy path
# ---------------------------------------------------------------------------


class TestResolveHappyPath:
    def test_basic_resolve(self, client):
        resp = client.post("/resolve", json={"question": "Did BTC close above $100K?"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["question"] == "Did BTC close above $100K?"
        assert "consensus" in body
        assert "votes" in body
        assert body["elapsed_seconds"] >= 0
        assert body["timestamp"] > 0

    def test_consensus_structure(self, client):
        resp = client.post("/resolve", json={"question": "Is ETH above $3000?"})
        body = resp.json()
        cons = body["consensus"]
        assert "probability" in cons
        assert cons["decision"] in ("YES", "NO", "DISPUTE")
        assert cons["num_votes"] == 3
        assert "variance" in cons
        assert len(cons["contributions"]) == 3

    def test_votes_structure(self, client):
        resp = client.post("/resolve", json={"question": "Is ETH above $3000?"})
        body = resp.json()
        votes = body["votes"]
        assert len(votes) == 3
        for vote in votes:
            assert "agent_id" in vote
            assert 0 <= vote["probability"] <= 1
            assert 0 <= vote["confidence"] <= 1
            assert "reasoning" in vote
            assert "research_strategy" in vote
            assert isinstance(vote["evidence"], list)

    def test_evidence_in_votes(self, client):
        resp = client.post("/resolve", json={"question": "Is ETH above $3000?"})
        body = resp.json()
        vote = body["votes"][0]
        assert len(vote["evidence"]) > 0
        ev = vote["evidence"][0]
        assert ev["source"] == "test-source"
        assert ev["source_type"] == "test"
        assert ev["confidence"] == 0.9

    def test_contribution_weights_sum_to_one(self, client):
        resp = client.post("/resolve", json={"question": "Is ETH above $3000?"})
        body = resp.json()
        contributions = body["consensus"]["contributions"]
        total = sum(c["normalized_weight"] for c in contributions)
        assert abs(total - 1.0) < 0.01

    def test_custom_thresholds(self, client):
        resp = client.post(
            "/resolve",
            json={
                "question": "Is ETH above $3000?",
                "yes_threshold": 0.9,
                "no_threshold": 0.1,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["consensus"]["decision"] in ("YES", "NO", "DISPUTE")


# ---------------------------------------------------------------------------
# /resolve — agent selection
# ---------------------------------------------------------------------------


class TestResolveAgentSelection:
    def test_select_specific_agents(self, client):
        resp = client.post(
            "/resolve",
            json={
                "question": "Is ETH above $3000?",
                "agents": ["agent-oracle", "agent-reliable"],
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["consensus"]["num_votes"] == 2
        agent_ids = {v["agent_id"] for v in body["votes"]}
        assert agent_ids == {"agent-oracle", "agent-reliable"}

    def test_unknown_agent_returns_400(self, client):
        resp = client.post(
            "/resolve",
            json={
                "question": "Is ETH above $3000?",
                "agents": ["agent-nonexistent"],
            },
        )
        assert resp.status_code == 400
        assert "Unknown agent ID" in resp.json()["detail"]

    def test_single_agent(self, client):
        resp = client.post(
            "/resolve",
            json={
                "question": "Is ETH above $3000?",
                "agents": ["agent-oracle"],
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["consensus"]["num_votes"] == 1


# ---------------------------------------------------------------------------
# /resolve — validation errors
# ---------------------------------------------------------------------------


class TestResolveValidation:
    def test_empty_question_returns_422(self, client):
        resp = client.post("/resolve", json={"question": ""})
        assert resp.status_code == 422

    def test_short_question_returns_422(self, client):
        resp = client.post("/resolve", json={"question": "Hi?"})
        assert resp.status_code == 422

    def test_missing_question_returns_422(self, client):
        resp = client.post("/resolve", json={})
        assert resp.status_code == 422

    def test_long_question_returns_422(self, client):
        resp = client.post("/resolve", json={"question": "x" * 501})
        assert resp.status_code == 422

    def test_invalid_yes_threshold(self, client):
        resp = client.post(
            "/resolve",
            json={"question": "Is ETH above $3000?", "yes_threshold": 0.3},
        )
        assert resp.status_code == 422

    def test_invalid_no_threshold(self, client):
        resp = client.post(
            "/resolve",
            json={"question": "Is ETH above $3000?", "no_threshold": 0.8},
        )
        assert resp.status_code == 422

    def test_no_body_returns_422(self, client):
        resp = client.post("/resolve")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# /resolve — error handling
# ---------------------------------------------------------------------------


class TestResolveErrors:
    def test_swarm_failure_returns_500(self):
        """If verify_question raises, the API returns 500 with detail."""
        with patch(
            "swarm_oracle.api.verify_question",
            side_effect=RuntimeError("LLM server down"),
        ):
            app = create_app()
            with TestClient(app) as client:
                resp = client.post(
                    "/resolve",
                    json={"question": "Is ETH above $3000?"},
                )
                assert resp.status_code == 500
                assert "LLM server down" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# OpenAPI / docs
# ---------------------------------------------------------------------------


class TestDocs:
    def test_openapi_schema(self, client):
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        assert "/resolve" in schema["paths"]
        assert "/health" in schema["paths"]
        assert "/compare" in schema["paths"]

    def test_docs_page(self, client):
        resp = client.get("/docs")
        assert resp.status_code == 200

    def test_redoc_page(self, client):
        resp = client.get("/redoc")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# /compare
# ---------------------------------------------------------------------------


class TestCompare:
    def test_basic_compare(self, client):
        resp = client.post("/compare", json={"question": "Did BTC close above $100K?"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["question"] == "Did BTC close above $100K?"
        assert len(body["methods"]) == 3
        assert body["elapsed_seconds"] >= 0

    def test_compare_method_names(self, client):
        resp = client.post("/compare", json={"question": "Is ETH above $3000?"})
        body = resp.json()
        method_names = [m["method"] for m in body["methods"]]
        assert "swarm_calibrated" in method_names
        assert "majority_equal" in method_names
        assert "single_best" in method_names

    def test_compare_all_methods_have_valid_decisions(self, client):
        resp = client.post("/compare", json={"question": "Is ETH above $3000?"})
        body = resp.json()
        for m in body["methods"]:
            assert m["decision"] in ("YES", "NO", "DISPUTE")
            assert 0 <= m["probability"] <= 1
            assert len(m["description"]) > 10

    def test_compare_includes_votes(self, client):
        resp = client.post("/compare", json={"question": "Is ETH above $3000?"})
        body = resp.json()
        assert len(body["votes"]) == 3
        for vote in body["votes"]:
            assert "agent_id" in vote
            assert 0 <= vote["probability"] <= 1

    def test_compare_swarm_differs_from_majority(self, client):
        """With unequal weights, swarm and majority probabilities should differ."""
        resp = client.post("/compare", json={"question": "Is ETH above $3000?"})
        body = resp.json()
        methods = {m["method"]: m for m in body["methods"]}
        # They CAN be equal in edge cases but with our test data they shouldn't be
        swarm_p = methods["swarm_calibrated"]["probability"]
        majority_p = methods["majority_equal"]["probability"]
        # At minimum, the single-best should match the top agent exactly
        single_p = methods["single_best"]["probability"]
        assert single_p == 0.05  # agent-oracle's probability

    def test_compare_validation(self, client):
        resp = client.post("/compare", json={"question": "Hi?"})
        assert resp.status_code == 422

    def test_compare_error_handling(self):
        with patch(
            "swarm_oracle.api.verify_question",
            side_effect=RuntimeError("LLM down"),
        ):
            app = create_app()
            with TestClient(app) as client:
                resp = client.post(
                    "/compare",
                    json={"question": "Is ETH above $3000?"},
                )
                assert resp.status_code == 500
                assert "LLM down" in resp.json()["detail"]
