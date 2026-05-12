"""FastAPI service for the Swarm Oracle protocol.

Exposes ``POST /resolve`` (single query) and ``POST /compare`` (swarm vs.
majority vs. single-agent ablation) endpoints.

Start with::

    uvicorn swarm_oracle.api:app --host 0.0.0.0 --port 8000

Or::

    python -m swarm_oracle.api          # convenience entry-point

Requires ``pip install 'swarm-oracle[api]'`` (fastapi + uvicorn).
"""
from __future__ import annotations

import logging
import time
from typing import Optional

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel, Field
except ImportError as exc:
    raise ImportError(
        "FastAPI dependencies not installed. "
        "Run: pip install 'swarm-oracle[api]'  "
        "(or: pip install fastapi uvicorn)"
    ) from exc

from .agent import SwarmAgent, default_swarm
from .consensus import AgentVote, ConsensusResult
from .verifier import SwarmResult, verify_question
from .weights import mock_brier_history, weights_from_history

log = logging.getLogger("swarm_oracle.api")

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class ResolveRequest(BaseModel):
    """POST body for ``/resolve``."""

    question: str = Field(
        ...,
        min_length=5,
        max_length=500,
        description="Binary (yes/no) prediction question to verify.",
        examples=["Did BTC close above $100K on May 5, 2026?"],
    )
    agents: Optional[list[str]] = Field(
        default=None,
        description=(
            "Optional list of agent IDs to include. "
            "If omitted, the default 3-agent swarm is used."
        ),
    )
    yes_threshold: Optional[float] = Field(
        default=None,
        ge=0.5,
        le=1.0,
        description="Probability threshold for YES decision (default 0.85).",
    )
    no_threshold: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=0.5,
        description="Probability threshold for NO decision (default 0.15).",
    )


class EvidenceResponse(BaseModel):
    source: str
    snippet: str
    source_type: str
    confidence: float


class VoteResponse(BaseModel):
    agent_id: str
    probability: float
    confidence: float
    reasoning: str
    research_strategy: str
    evidence: list[EvidenceResponse]


class ContributionResponse(BaseModel):
    agent_id: str
    probability: float
    weight: float
    normalized_weight: float


class ConsensusResponse(BaseModel):
    probability: float
    decision: str
    num_votes: int
    variance: float
    dispute_reason: Optional[str] = None
    contributions: list[ContributionResponse]


class ResolveResponse(BaseModel):
    """Full response for ``/resolve``."""

    question: str
    consensus: ConsensusResponse
    votes: list[VoteResponse]
    elapsed_seconds: float
    timestamp: float


class HealthResponse(BaseModel):
    status: str
    version: str
    agents: int


class CompareRequest(BaseModel):
    """POST body for ``/compare``."""

    question: str = Field(
        ...,
        min_length=5,
        max_length=500,
        description="Binary (yes/no) prediction question to compare methods on.",
    )


class MethodResult(BaseModel):
    """Result from one aggregation method."""

    method: str
    probability: float
    decision: str
    description: str


class CompareResponse(BaseModel):
    """Side-by-side comparison of aggregation methods."""

    question: str
    methods: list[MethodResult]
    votes: list[VoteResponse]
    elapsed_seconds: float


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    """Build the FastAPI application with CORS and routes."""

    app = FastAPI(
        title="Swarm Oracle API",
        description=(
            "Calibration-weighted multi-agent prediction oracle. "
            "Submit a binary question and receive a consensus probability "
            "computed from multiple AI agents with Brier-score calibration weights."
        ),
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Cache the default swarm + weights so we don't rebuild per request.
    _default_agents: list[SwarmAgent] = default_swarm()
    _default_weights: dict[str, float] = weights_from_history(mock_brier_history())

    # -----------------------------------------------------------------------
    # Routes
    # -----------------------------------------------------------------------

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        """Liveness / readiness check."""
        return HealthResponse(
            status="ok",
            version="0.1.0",
            agents=len(_default_agents),
        )

    @app.post("/resolve", response_model=ResolveResponse)
    async def resolve(req: ResolveRequest) -> ResolveResponse:
        """Run the Swarm Oracle on a binary question.

        The swarm fans out the question to multiple agents in parallel,
        collects their probability estimates and evidence, then aggregates
        via a calibration-weighted linear opinion pool.
        """
        # Select agents
        if req.agents:
            agent_map = {a.agent_id: a for a in _default_agents}
            agents = []
            for aid in req.agents:
                if aid not in agent_map:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Unknown agent ID: {aid}. "
                        f"Available: {sorted(agent_map.keys())}",
                    )
                agents.append(agent_map[aid])
        else:
            agents = _default_agents

        # Build threshold kwargs
        threshold_kwargs: dict = {}
        if req.yes_threshold is not None:
            threshold_kwargs["yes_threshold"] = req.yes_threshold
        if req.no_threshold is not None:
            threshold_kwargs["no_threshold"] = req.no_threshold

        # Run the swarm (blocking I/O in threadpool — fine for demo)
        try:
            result: SwarmResult = verify_question(
                question=req.question,
                agents=agents,
                weights=_default_weights,
                **threshold_kwargs,
            )
        except Exception as exc:
            log.exception("Swarm execution failed")
            raise HTTPException(
                status_code=500,
                detail=f"Swarm execution failed: {exc}",
            ) from exc

        # Serialize
        return ResolveResponse(
            question=result.question,
            consensus=_serialize_consensus(result.consensus),
            votes=[_serialize_vote(v) for v in result.votes],
            elapsed_seconds=round(result.elapsed_seconds, 3),
            timestamp=time.time(),
        )

    @app.post("/compare", response_model=CompareResponse)
    async def compare(req: CompareRequest) -> CompareResponse:
        """Compare swarm (calibration-weighted) vs. majority vote vs. single agent.

        Runs the full swarm once, then re-aggregates the same votes using
        three strategies so judges can see the value of calibration weighting.
        """
        from .consensus import aggregate_consensus as _agg

        try:
            result: SwarmResult = verify_question(
                question=req.question,
                agents=_default_agents,
                weights=_default_weights,
            )
        except Exception as exc:
            log.exception("Swarm execution failed")
            raise HTTPException(
                status_code=500,
                detail=f"Compare execution failed: {exc}",
            ) from exc

        votes = result.votes

        # Method 1: Calibration-weighted (the real thing)
        swarm_cons = result.consensus

        # Method 2: Equal-weight majority (every agent gets weight 1.0)
        equal_weights = {v.agent_id: 1.0 for v in votes}
        majority_cons = _agg(votes, equal_weights)

        # Method 3: Single best agent (highest-weight agent only)
        best_agent = max(
            votes,
            key=lambda v: _default_weights.get(v.agent_id, 0.0),
        )
        single_cons = _agg([best_agent], _default_weights)

        def _decision_label(prob: float, decision: str) -> str:
            return f"{decision} (P={prob:.3f})"

        methods = [
            MethodResult(
                method="swarm_calibrated",
                probability=round(swarm_cons.probability, 6),
                decision=swarm_cons.decision,
                description=(
                    "Calibration-weighted linear opinion pool. "
                    "Better-calibrated agents (lower Brier score) get more influence."
                ),
            ),
            MethodResult(
                method="majority_equal",
                probability=round(majority_cons.probability, 6),
                decision=majority_cons.decision,
                description=(
                    "Equal-weight average. Every agent has the same influence "
                    "regardless of track record."
                ),
            ),
            MethodResult(
                method="single_best",
                probability=round(single_cons.probability, 6),
                decision=single_cons.decision,
                description=(
                    f"Single agent ({best_agent.agent_id}) — the one with "
                    f"the best calibration history. No diversity benefit."
                ),
            ),
        ]

        return CompareResponse(
            question=result.question,
            methods=methods,
            votes=[_serialize_vote(v) for v in votes],
            elapsed_seconds=round(result.elapsed_seconds, 3),
        )

    return app


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _serialize_consensus(c: ConsensusResult) -> ConsensusResponse:
    return ConsensusResponse(
        probability=round(c.probability, 6),
        decision=c.decision,
        num_votes=c.num_votes,
        variance=round(c.variance, 6),
        dispute_reason=c.dispute_reason,
        contributions=[
            ContributionResponse(
                agent_id=ct.agent_id,
                probability=round(ct.probability, 6),
                weight=round(ct.weight, 4),
                normalized_weight=round(ct.normalized_weight, 4),
            )
            for ct in c.contributions
        ],
    )


def _serialize_vote(v: AgentVote) -> VoteResponse:
    return VoteResponse(
        agent_id=v.agent_id,
        probability=round(v.probability, 6),
        confidence=round(v.confidence, 6),
        reasoning=v.reasoning,
        research_strategy=v.research_strategy,
        evidence=[
            EvidenceResponse(
                source=e.source,
                snippet=e.snippet[:500],
                source_type=e.source_type,
                confidence=round(e.confidence, 4),
            )
            for e in v.evidence
        ],
    )


# ---------------------------------------------------------------------------
# Module-level app instance (for uvicorn swarm_oracle.api:app)
# ---------------------------------------------------------------------------

app = create_app()


# ---------------------------------------------------------------------------
# Convenience entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "swarm_oracle.api:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
