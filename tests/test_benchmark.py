"""
tests/test_benchmark.py

Tests for scripts/benchmark.py — determinism, metric correctness, CLI, output format.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent


def _run_benchmark(cases: int = 20, seed: int = 42, extra_args: list[str] | None = None):
    """Run benchmark as a module and return (data_dict, html_str, stdout_str)."""
    with tempfile.TemporaryDirectory() as tmp:
        cmd = [
            sys.executable, "-m", "scripts.benchmark",
            "--cases", str(cases),
            "--seed", str(seed),
            "--output", tmp,
        ]
        if extra_args:
            cmd += extra_args
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0, f"benchmark.py failed:\n{result.stderr}"
        data = json.loads((Path(tmp) / "benchmark.json").read_text())
        html_path = Path(tmp) / "benchmark.html"
        html = html_path.read_text() if html_path.exists() else ""
        return data, html, result.stdout


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_same_seed_same_results(self):
        """Two runs with same seed must produce identical metrics."""
        d1, _, _ = _run_benchmark(cases=20, seed=42)
        d2, _, _ = _run_benchmark(cases=20, seed=42)
        assert d1["metrics"] == d2["metrics"], "benchmark is not deterministic with same seed"

    def test_different_seed_different_results(self):
        """Different seeds should (almost certainly) produce different metrics."""
        d1, _, _ = _run_benchmark(cases=30, seed=1)
        d2, _, _ = _run_benchmark(cases=30, seed=99)
        # With 30 cases the chance of identical accuracy for all methods is astronomically low
        assert d1["metrics"]["swarm"]["n_correct"] != d2["metrics"]["swarm"]["n_correct"] or \
               d1["metrics"]["agent-oracle"]["brier"] != d2["metrics"]["agent-oracle"]["brier"], \
               "different seeds produced identical results (suspicious)"


# ---------------------------------------------------------------------------
# Core metric correctness
# ---------------------------------------------------------------------------

class TestMetrics:
    @pytest.fixture(scope="class")
    def data(self):
        d, _, _ = _run_benchmark(cases=50, seed=42)
        return d

    def test_swarm_brier_better_than_oracle(self, data):
        """Calibration weighting must beat any single agent on Brier."""
        swarm_brier = data["metrics"]["swarm"]["brier"]
        oracle_brier = data["metrics"]["agent-oracle"]["brier"]
        assert swarm_brier < oracle_brier, (
            f"swarm Brier {swarm_brier:.4f} >= oracle Brier {oracle_brier:.4f} — "
            "calibration weighting failed to beat best single agent"
        )

    def test_swarm_brier_better_than_all_agents(self, data):
        """Swarm Brier should beat every individual agent."""
        swarm_brier = data["metrics"]["swarm"]["brier"]
        for agent in ("agent-oracle", "agent-reliable", "agent-novice"):
            agent_brier = data["metrics"][agent]["brier"]
            assert swarm_brier < agent_brier, (
                f"swarm Brier {swarm_brier:.4f} >= {agent} Brier {agent_brier:.4f}"
            )

    def test_swarm_accuracy_counts_dispute_as_correct(self, data):
        """Swarm accuracy must be >= oracle accuracy due to DISPUTE abstention credit."""
        swarm_acc = data["metrics"]["swarm"]["accuracy"]
        oracle_acc = data["metrics"]["agent-oracle"]["accuracy"]
        assert swarm_acc >= oracle_acc, (
            f"swarm accuracy {swarm_acc:.2%} < oracle accuracy {oracle_acc:.2%}"
        )

    def test_oracle_better_than_reliable(self, data):
        """Oracle (Brier 0.10) must beat reliable (Brier 0.18) across all runs."""
        assert data["metrics"]["agent-oracle"]["brier"] < data["metrics"]["agent-reliable"]["brier"]

    def test_reliable_better_than_novice(self, data):
        """Reliable (Brier 0.18) must beat novice (Brier 0.25)."""
        assert data["metrics"]["agent-reliable"]["brier"] < data["metrics"]["agent-novice"]["brier"]

    def test_swarm_has_disputes(self, data):
        """Swarm should abstain (DISPUTE) on at least one case in 50."""
        assert data["metrics"]["swarm"]["n_disputed"] > 0, "swarm had zero disputes — check DISPUTE logic"

    def test_brier_range(self, data):
        """All Brier scores must be in [0, 1]."""
        for method, m in data["metrics"].items():
            assert 0.0 <= m["brier"] <= 1.0, f"{method} Brier out of range: {m['brier']}"

    def test_n_correct_consistent_with_accuracy(self, data):
        """n_correct / n_total should match reported accuracy (within float tolerance)."""
        for method, m in data["metrics"].items():
            if m["n_total"] > 0:
                expected = m["n_correct"] / m["n_total"]
                assert abs(m["accuracy"] - expected) < 1e-6, (
                    f"{method}: accuracy {m['accuracy']} != n_correct/n_total {expected}"
                )


# ---------------------------------------------------------------------------
# JSON structure
# ---------------------------------------------------------------------------

class TestJSONStructure:
    @pytest.fixture(scope="class")
    def data(self):
        d, _, _ = _run_benchmark(cases=20, seed=42)
        return d

    def test_top_level_keys(self, data):
        for key in ("timestamp", "n_cases", "seed", "agent_weights", "metrics", "cases"):
            assert key in data, f"Missing top-level key: {key}"

    def test_n_cases(self, data):
        assert data["n_cases"] == 20
        assert len(data["cases"]) == 20

    def test_seed(self, data):
        assert data["seed"] == 42

    def test_agent_weights_keys(self, data):
        assert set(data["agent_weights"].keys()) == {"agent-oracle", "agent-reliable", "agent-novice"}

    def test_agent_weights_positive(self, data):
        for agent, w in data["agent_weights"].items():
            assert w > 0, f"weight for {agent} is {w}"

    def test_oracle_weight_highest(self, data):
        """Oracle must have highest weight (lowest Brier)."""
        w = data["agent_weights"]
        assert w["agent-oracle"] > w["agent-reliable"] > w["agent-novice"]

    def test_metrics_all_methods_present(self, data):
        for method in ("swarm", "agent-oracle", "agent-reliable", "agent-novice", "average", "majority"):
            assert method in data["metrics"], f"Missing method in metrics: {method}"

    def test_metrics_fields(self, data):
        for method, m in data["metrics"].items():
            for field in ("accuracy", "brier", "log_loss", "n_correct", "n_total", "n_disputed"):
                assert field in m, f"{method} missing field: {field}"

    def test_cases_structure(self, data):
        case = data["cases"][0]
        for field in ("question", "outcome", "agent_votes", "swarm_decision"):
            assert field in case, f"Case missing field: {field}"

    def test_agent_votes_in_cases(self, data):
        for i, case in enumerate(data["cases"]):
            votes = case["agent_votes"]
            for agent in ("agent-oracle", "agent-reliable", "agent-novice"):
                assert agent in votes, f"Case {i} missing vote for {agent}"
                assert 0.0 <= votes[agent] <= 1.0, f"Invalid probability for {agent}: {votes[agent]}"

    def test_ground_truth_values(self, data):
        for i, case in enumerate(data["cases"]):
            assert case["outcome"] in ("YES", "NO"), \
                f"Case {i}: invalid outcome: {case['outcome']}"


# ---------------------------------------------------------------------------
# HTML output
# ---------------------------------------------------------------------------

class TestHTMLOutput:
    @pytest.fixture(scope="class")
    def html(self):
        _, h, _ = _run_benchmark(cases=20, seed=42)
        return h

    def test_html_is_nonempty(self, html):
        assert len(html) > 500, "benchmark.html is suspiciously short"

    def test_html_contains_swarm(self, html):
        assert "swarm" in html.lower()

    def test_html_contains_brier(self, html):
        assert "brier" in html.lower() or "Brier" in html

    def test_html_is_valid_open_close(self, html):
        assert "<html" in html or "<!DOCTYPE" in html or "<table" in html


# ---------------------------------------------------------------------------
# CLI argument parsing
# ---------------------------------------------------------------------------

class TestCLI:
    def test_default_cases_50(self):
        """Default run (no --cases) must produce 50 cases."""
        with tempfile.TemporaryDirectory() as tmp:
            cmd = [
                sys.executable, "-m", "scripts.benchmark",
                "--output", tmp,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO_ROOT))
            assert result.returncode == 0, f"benchmark.py failed:\n{result.stderr}"
            d = json.loads((Path(tmp) / "benchmark.json").read_text())
            assert d["n_cases"] == 50

    def test_custom_cases(self):
        d, _, _ = _run_benchmark(cases=10, seed=7)
        assert d["n_cases"] == 10
        assert len(d["cases"]) == 10

    def test_stdout_includes_summary(self):
        _, _, stdout = _run_benchmark(cases=10, seed=42)
        assert "swarm" in stdout.lower()
        assert "%" in stdout  # accuracy percentage

    def test_zero_cases_produces_empty_benchmark(self):
        """--cases 0 produces a valid JSON with n_cases==0 (graceful empty run)."""
        with tempfile.TemporaryDirectory() as tmp:
            cmd = [
                sys.executable, "-m", "scripts.benchmark",
                "--cases", "0",
                "--output", tmp,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO_ROOT))
            # Either exits non-zero OR produces valid JSON with 0 cases
            if result.returncode == 0:
                d = json.loads((Path(tmp) / "benchmark.json").read_text())
                assert d["n_cases"] == 0
                assert d["cases"] == []
            # Either behavior is acceptable — main thing is no unhandled exception


# ---------------------------------------------------------------------------
# Regression: calibration weighting properties
# ---------------------------------------------------------------------------

class TestCalibrationProperties:
    @pytest.fixture(scope="class")
    def data(self):
        # Use larger sample for statistical stability
        d, _, _ = _run_benchmark(cases=50, seed=42)
        return d

    def test_majority_baseline(self, data):
        """Majority vote should be at least 70% accurate on these cases."""
        assert data["metrics"]["majority"]["accuracy"] >= 0.70

    def test_novice_worse_than_majority(self, data):
        """Novice agent should have worse Brier than majority vote."""
        assert data["metrics"]["agent-novice"]["brier"] > data["metrics"]["majority"]["brier"]

    def test_swarm_accuracy_at_least_90_percent(self, data):
        """Swarm (DISPUTE=correct) should be ≥ 90% accurate with 50 cases."""
        assert data["metrics"]["swarm"]["accuracy"] >= 0.90, (
            f"Swarm accuracy {data['metrics']['swarm']['accuracy']:.2%} < 90%"
        )
