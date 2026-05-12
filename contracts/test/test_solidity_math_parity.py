"""Cross-verification: Solidity fixed-point math vs. Python reference implementation.

Validates that CalibrationRegistry.sol and SwarmConsensus.sol produce the same
results as swarm_oracle/weights.py and swarm_oracle/consensus.py.

No Solidity toolchain required — tests pure math with WAD-scaled integers.
"""
import sys
import os
import math

# Add repo root so we can import swarm_oracle
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../scripts"))

from swarm_oracle.weights import (
    compute_weight,
    update_brier_running_average,
    BASE_WEIGHT,
    MIN_PREDICTIONS,
    CONFIDENCE_THRESHOLD,
    EPSILON,
)
from swarm_oracle.consensus import aggregate_consensus, AgentVote

# ---------------------------------------------------------------------------
# Constants (mirror Solidity)
# ---------------------------------------------------------------------------

WAD = 10**18
SOL_EPSILON = 10**15  # 0.001 in WAD
SOL_MIN_PREDICTIONS = 20
SOL_CONFIDENCE_THRESHOLD = 100
SOL_MAX_BRIER = WAD


def sol_compute_weight(brier_wad: int, n: int) -> int:
    """Python replica of CalibrationRegistry._computeWeight."""
    if n < SOL_MIN_PREDICTIONS:
        return WAD

    raw = (WAD * WAD) // (brier_wad + SOL_EPSILON)
    confidence = (n * WAD) // SOL_CONFIDENCE_THRESHOLD
    if confidence > WAD:
        confidence = WAD
    return (raw * confidence) // WAD


def sol_update_brier(prior_brier_wad: int | None, prior_n: int, prediction_wad: int, outcome_wad: int):
    """Python replica of CalibrationRegistry.updateBrier."""
    diff = abs(prediction_wad - outcome_wad)
    brier_term = (diff * diff) // WAD

    if prior_brier_wad is None or prior_n == 0:
        return (brier_term, 1)

    new_n = prior_n + 1
    new_brier = (prior_brier_wad * prior_n + brier_term) // new_n
    return (new_brier, new_n)


def to_wad(x: float) -> int:
    return int(x * WAD)


def from_wad(x: int) -> float:
    return x / WAD


# ---------------------------------------------------------------------------
# Tests: Weight computation parity
# ---------------------------------------------------------------------------

def test_weight_new_agent():
    """Unknown agent gets BASE_WEIGHT = 1.0 in both implementations."""
    py_w = compute_weight(0.25, 10)  # n < MIN_PREDICTIONS
    sol_w = sol_compute_weight(to_wad(0.25), 10)
    assert py_w == BASE_WEIGHT, f"Python: {py_w} != {BASE_WEIGHT}"
    assert sol_w == WAD, f"Solidity: {sol_w} != {WAD}"
    print("  PASS: new agent → BASE_WEIGHT")


def test_weight_perfect_brier():
    """Perfect Brier (0.0), n=100 → weight = 1/(0+0.001) * 1.0 = 1000."""
    py_w = compute_weight(0.0, 100)
    sol_w = sol_compute_weight(0, 100)

    expected_py = 1.0 / (0.0 + EPSILON)  # = 1000.0
    assert abs(py_w - expected_py) < 1e-6, f"Python: {py_w} != {expected_py}"
    assert sol_w == 1000 * WAD, f"Solidity: {sol_w} != {1000 * WAD}"
    print("  PASS: perfect brier → weight 1000")


def test_weight_mid_brier():
    """Brier=0.25, n=100 → weight ≈ 3.984."""
    py_w = compute_weight(0.25, 100)
    sol_w = sol_compute_weight(to_wad(0.25), 100)

    expected = 1.0 / (0.25 + EPSILON)  # ≈ 3.984
    assert abs(py_w - expected) < 1e-6
    # Solidity integer division may differ slightly
    sol_float = from_wad(sol_w)
    assert abs(sol_float - expected) < 0.01, f"Solidity {sol_float} vs Python {expected}"
    print(f"  PASS: mid brier → py={py_w:.4f}, sol={sol_float:.4f}")


def test_weight_confidence_scaling():
    """Brier=0.10, n=50 → half confidence."""
    py_w = compute_weight(0.10, 50)
    sol_w = sol_compute_weight(to_wad(0.10), 50)

    raw = 1.0 / (0.10 + EPSILON)
    conf = 50 / CONFIDENCE_THRESHOLD
    expected = raw * conf
    assert abs(py_w - expected) < 1e-6
    sol_float = from_wad(sol_w)
    assert abs(sol_float - expected) < 0.01, f"Solidity {sol_float} vs Python {expected}"
    print(f"  PASS: confidence scaling → py={py_w:.4f}, sol={sol_float:.4f}")


def test_weight_boundary_min_predictions():
    """At exactly MIN_PREDICTIONS, weight is computed (not base)."""
    py_w = compute_weight(0.20, 20)
    sol_w = sol_compute_weight(to_wad(0.20), 20)

    # n=20 >= MIN_PREDICTIONS, so formula applies
    raw = 1.0 / (0.20 + EPSILON)
    conf = 20 / CONFIDENCE_THRESHOLD
    expected = raw * conf
    assert abs(py_w - expected) < 1e-6
    sol_float = from_wad(sol_w)
    assert abs(sol_float - expected) < 0.01
    print(f"  PASS: boundary n=20 → py={py_w:.4f}, sol={sol_float:.4f}")


# ---------------------------------------------------------------------------
# Tests: Brier update parity
# ---------------------------------------------------------------------------

def test_brier_update_first():
    """First prediction: p=0.8, outcome=YES → brier=0.04."""
    py_b, py_n = update_brier_running_average(None, 0, 0.8, 1.0)
    sol_b, sol_n = sol_update_brier(None, 0, to_wad(0.8), WAD)

    assert py_n == 1 and sol_n == 1
    assert abs(py_b - 0.04) < 1e-10
    assert sol_b == to_wad(0.04), f"Solidity: {sol_b} != {to_wad(0.04)}"
    print("  PASS: first update → brier=0.04")


def test_brier_update_running_average():
    """Two predictions: running average."""
    py_b, py_n = update_brier_running_average(None, 0, 0.8, 1.0)
    py_b, py_n = update_brier_running_average(py_b, py_n, 0.3, 0.0)

    sol_b, sol_n = sol_update_brier(None, 0, to_wad(0.8), WAD)
    sol_b, sol_n = sol_update_brier(sol_b, sol_n, to_wad(0.3), 0)

    assert py_n == 2 and sol_n == 2
    expected = (0.04 + 0.09) / 2  # = 0.065
    assert abs(py_b - expected) < 1e-10
    assert sol_b == to_wad(0.065), f"Solidity: {sol_b} != {to_wad(0.065)}"
    print(f"  PASS: running average → py={py_b:.4f}, sol={from_wad(sol_b):.4f}")


def test_brier_update_wrong_prediction():
    """Terrible prediction: p=0.9 YES, outcome=NO → 0.81."""
    py_b, py_n = update_brier_running_average(None, 0, 0.9, 0.0)
    sol_b, sol_n = sol_update_brier(None, 0, to_wad(0.9), 0)

    assert abs(py_b - 0.81) < 1e-10
    assert sol_b == to_wad(0.81)
    print("  PASS: wrong prediction → brier=0.81")


# ---------------------------------------------------------------------------
# Tests: Consensus aggregation parity (math only, not full Solidity execution)
# ---------------------------------------------------------------------------

def test_consensus_weighted_mean():
    """Verify weighted mean formula produces consistent results."""
    # Three agents with different calibrations
    votes = [
        AgentVote("a1", probability=0.90, confidence=0.9),
        AgentVote("a2", probability=0.85, confidence=0.8),
        AgentVote("a3", probability=0.70, confidence=0.7),
    ]
    weights = {
        "a1": compute_weight(0.10, 220),  # best calibrated → highest weight
        "a2": compute_weight(0.18, 140),  # mid
        "a3": compute_weight(0.25, 25),   # low confidence
    }

    result = aggregate_consensus(votes, weights)

    # Simulate Solidity fixed-point
    sol_weights = [
        sol_compute_weight(to_wad(0.10), 220),
        sol_compute_weight(to_wad(0.18), 140),
        sol_compute_weight(to_wad(0.25), 25),
    ]
    probs_wad = [to_wad(0.90), to_wad(0.85), to_wad(0.70)]
    total_w = sum(sol_weights)

    weighted_sum = sum(
        (p * w) // WAD for p, w in zip(probs_wad, sol_weights)
    )
    sol_consensus = (weighted_sum * WAD) // total_w

    # Compare
    py_prob = result.probability
    sol_prob = from_wad(sol_consensus)

    assert abs(py_prob - sol_prob) < 0.01, (
        f"Consensus mismatch: py={py_prob:.4f}, sol={sol_prob:.4f}"
    )
    print(f"  PASS: weighted consensus → py={py_prob:.4f}, sol={sol_prob:.4f}")


def test_consensus_decision_yes():
    """Strong YES consensus → decision=YES."""
    votes = [
        AgentVote("a1", probability=0.95, confidence=0.9),
        AgentVote("a2", probability=0.92, confidence=0.9),
        AgentVote("a3", probability=0.88, confidence=0.8),
    ]
    weights = {"a1": 10.0, "a2": 5.0, "a3": 3.0}
    result = aggregate_consensus(votes, weights)
    assert result.decision == "YES", f"Expected YES, got {result.decision}"
    print(f"  PASS: strong YES consensus → p={result.probability:.4f}")


def test_consensus_decision_no():
    """Strong NO consensus → decision=NO."""
    votes = [
        AgentVote("a1", probability=0.05, confidence=0.9),
        AgentVote("a2", probability=0.08, confidence=0.9),
        AgentVote("a3", probability=0.12, confidence=0.8),
    ]
    weights = {"a1": 10.0, "a2": 5.0, "a3": 3.0}
    result = aggregate_consensus(votes, weights)
    assert result.decision == "NO", f"Expected NO, got {result.decision}"
    print(f"  PASS: strong NO consensus → p={result.probability:.4f}")


def test_consensus_decision_dispute_variance():
    """High disagreement → DISPUTE even if mean looks decisive."""
    votes = [
        AgentVote("a1", probability=0.95, confidence=0.9),  # strong YES
        AgentVote("a2", probability=0.10, confidence=0.9),  # strong NO
        AgentVote("a3", probability=0.50, confidence=0.5),  # neutral
    ]
    weights = {"a1": 5.0, "a2": 5.0, "a3": 5.0}  # equal weights
    result = aggregate_consensus(votes, weights)
    assert result.decision == "DISPUTE", f"Expected DISPUTE, got {result.decision}"
    print(f"  PASS: high variance → DISPUTE (var={result.variance:.4f})")


def test_consensus_decision_dispute_threshold():
    """Mean between thresholds → DISPUTE."""
    votes = [
        AgentVote("a1", probability=0.50, confidence=0.5),
        AgentVote("a2", probability=0.55, confidence=0.5),
    ]
    weights = {"a1": 1.0, "a2": 1.0}
    result = aggregate_consensus(votes, weights)
    assert result.decision == "DISPUTE", f"Expected DISPUTE, got {result.decision}"
    print(f"  PASS: ambiguous mean → DISPUTE (p={result.probability:.4f})")


# ---------------------------------------------------------------------------
# Tests: Mock history parity
# ---------------------------------------------------------------------------

def test_mock_history_weights():
    """Verify mock_brier_history weights are correctly ordered."""
    from swarm_oracle.weights import mock_brier_history, weights_from_history
    history = mock_brier_history()
    weights = weights_from_history(history)

    # agent-oracle (brier=0.10, n=220) should have highest weight
    # agent-reliable (brier=0.18, n=140) should be mid
    # agent-novice (brier=0.25, n=25) should be lowest (low confidence)
    assert weights["agent-oracle"] > weights["agent-reliable"] > weights["agent-novice"], (
        f"Weight ordering wrong: {weights}"
    )
    print(f"  PASS: mock history weights ordered correctly: "
          f"oracle={weights['agent-oracle']:.2f}, "
          f"reliable={weights['agent-reliable']:.2f}, "
          f"novice={weights['agent-novice']:.2f}")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def main():
    tests = [
        ("Weight: new agent", test_weight_new_agent),
        ("Weight: perfect brier", test_weight_perfect_brier),
        ("Weight: mid brier", test_weight_mid_brier),
        ("Weight: confidence scaling", test_weight_confidence_scaling),
        ("Weight: boundary n=20", test_weight_boundary_min_predictions),
        ("Brier update: first", test_brier_update_first),
        ("Brier update: running average", test_brier_update_running_average),
        ("Brier update: wrong prediction", test_brier_update_wrong_prediction),
        ("Consensus: weighted mean", test_consensus_weighted_mean),
        ("Consensus: YES decision", test_consensus_decision_yes),
        ("Consensus: NO decision", test_consensus_decision_no),
        ("Consensus: DISPUTE (variance)", test_consensus_decision_dispute_variance),
        ("Consensus: DISPUTE (threshold)", test_consensus_decision_dispute_threshold),
        ("Mock history: weight ordering", test_mock_history_weights),
    ]

    passed = 0
    failed = 0

    for name, fn in tests:
        try:
            fn()
            passed += 1
        except Exception as e:
            print(f"  FAIL: {name}: {e}")
            failed += 1

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")
    if failed:
        sys.exit(1)
    else:
        print("All parity tests passed!")


if __name__ == "__main__":
    main()
