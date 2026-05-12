"""Swarm Oracle — calibration-weighted multi-agent verification protocol.

Public API:

    from swarm_oracle import (
        SwarmAgent,
        AgentVote,
        ConsensusResult,
        Evidence,
        aggregate_consensus,
        compute_weight,
        verify_question,
    )
"""
from .agent import SwarmAgent, default_swarm
from .consensus import (
    AgentVote,
    ConsensusResult,
    Contribution,
    Evidence,
    aggregate_consensus,
)
from .verifier import SwarmResult, verify_question
from .weights import (
    BASE_WEIGHT,
    MIN_PREDICTIONS,
    compute_weight,
    mock_brier_history,
    update_brier_running_average,
    weights_from_history,
)

__all__ = [
    "AgentVote",
    "BASE_WEIGHT",
    "ConsensusResult",
    "Contribution",
    "Evidence",
    "MIN_PREDICTIONS",
    "SwarmAgent",
    "SwarmResult",
    "aggregate_consensus",
    "compute_weight",
    "default_swarm",
    "mock_brier_history",
    "update_brier_running_average",
    "verify_question",
    "weights_from_history",
]
