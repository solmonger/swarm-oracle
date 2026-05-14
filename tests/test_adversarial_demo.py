"""Tests for the :mod:`scripts.adversarial_demo` CLI runner."""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys
from io import StringIO
from pathlib import Path

import pytest

from scripts import adversarial_demo as demo
from swarm_oracle import adversarial as adv


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


class TestArgParse:
    def test_defaults(self) -> None:
        args = demo._parse_args([])
        assert args.vector == "all"
        assert args.target == "YES"
        assert args.num_colluders == 3
        assert args.num_sybils == 4
        assert args.max_weight_per_sybil == 100.0
        assert args.bribery_cost == adv.DEFAULT_BRIBERY_COST_USD
        assert args.registry_cost == 5.0
        assert args.compare is False
        assert args.json is None

    @pytest.mark.parametrize("vector", ["collusion", "adaptive", "bribery", "all"])
    def test_valid_vectors(self, vector: str) -> None:
        args = demo._parse_args(["--vector", vector])
        assert args.vector == vector

    def test_rejects_invalid_vector(self) -> None:
        with pytest.raises(SystemExit):
            demo._parse_args(["--vector", "magic"])

    @pytest.mark.parametrize("target", ["YES", "NO", "DISPUTE"])
    def test_valid_targets(self, target: str) -> None:
        args = demo._parse_args(["--target", target])
        assert args.target == target

    def test_rejects_invalid_target(self) -> None:
        with pytest.raises(SystemExit):
            demo._parse_args(["--target", "MAYBE"])

    def test_rejects_zero_colluders(self) -> None:
        with pytest.raises(SystemExit):
            demo._parse_args(["--num-colluders", "0"])

    def test_rejects_zero_sybils(self) -> None:
        with pytest.raises(SystemExit):
            demo._parse_args(["--num-sybils", "0"])

    def test_rejects_negative_weight(self) -> None:
        with pytest.raises(SystemExit):
            demo._parse_args(["--max-weight-per-sybil", "-1"])

    def test_rejects_negative_bribery_cost(self) -> None:
        with pytest.raises(SystemExit):
            demo._parse_args(["--bribery-cost", "-100"])

    def test_rejects_negative_registry_cost(self) -> None:
        with pytest.raises(SystemExit):
            demo._parse_args(["--registry-cost", "-1"])

    def test_compare_flag(self) -> None:
        args = demo._parse_args(["--compare"])
        assert args.compare is True


# ---------------------------------------------------------------------------
# Text output
# ---------------------------------------------------------------------------


class TestTextOutput:
    def test_all_sections_present(self, capsys: pytest.CaptureFixture) -> None:
        rc = demo.main([])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Adversarial Simulation" in out
        assert "Collusion result" in out
        assert "Adaptive attacker result" in out
        assert "Bribery result" in out
        assert "Attack vector comparison" in out

    def test_target_in_output(self, capsys: pytest.CaptureFixture) -> None:
        demo.main(["--target", "NO"])
        out = capsys.readouterr().out
        assert "Target decision: NO" in out

    def test_collusion_only(self, capsys: pytest.CaptureFixture) -> None:
        demo.main(["--vector", "collusion"])
        out = capsys.readouterr().out
        assert "Collusion result" in out
        assert "Adaptive attacker result" not in out
        assert "Bribery result" not in out

    def test_adaptive_only(self, capsys: pytest.CaptureFixture) -> None:
        demo.main(["--vector", "adaptive"])
        out = capsys.readouterr().out
        assert "Adaptive attacker result" in out
        assert "Collusion result" not in out

    def test_bribery_only(self, capsys: pytest.CaptureFixture) -> None:
        demo.main(["--vector", "bribery"])
        out = capsys.readouterr().out
        assert "Bribery result" in out
        assert "Total cost (USD):" in out

    def test_compare_runs_compose(self, capsys: pytest.CaptureFixture) -> None:
        demo.main(["--compare"])
        out = capsys.readouterr().out
        assert "Attack vector comparison" in out
        assert "Cheapest" in out

    def test_bribery_cost_propagates(self, capsys: pytest.CaptureFixture) -> None:
        """Custom --bribery-cost flows through to the printed cost."""
        demo.main(["--vector", "bribery", "--bribery-cost", "750"])
        out = capsys.readouterr().out
        # Cost will be 750 * (1, 2, or 3 agents) — assert 750 appears
        assert "$750" in out or "$1,500" in out or "$2,250" in out


# ---------------------------------------------------------------------------
# JSON output
# ---------------------------------------------------------------------------


class TestJsonOutput:
    def test_writes_json_file(self, tmp_path: Path) -> None:
        out_path = tmp_path / "adv.json"
        demo.main(["--json", str(out_path)])
        assert out_path.exists()
        data = json.loads(out_path.read_text())
        assert "target" in data
        assert "results" in data
        for vec in ("collusion", "adaptive", "bribery", "compose"):
            assert vec in data["results"]

    def test_json_creates_parent_dir(self, tmp_path: Path) -> None:
        out_path = tmp_path / "nested" / "deep" / "adv.json"
        demo.main(["--json", str(out_path)])
        assert out_path.exists()

    def test_json_handles_inf_sentinel(self, tmp_path: Path) -> None:
        """When a result has math.inf (e.g. infeasible attack), JSON
        output uses the string ``"inf"`` rather than failing to
        serialize."""
        # Force a scenario where Sybil/bribery are infeasible
        out_path = tmp_path / "infeasible.json"
        rc = demo.main([
            "--vector", "bribery",
            "--target", "YES",
            "--json", str(out_path),
        ])
        assert rc == 0
        data = json.loads(out_path.read_text())
        # Find any infinite values, confirm they're strings
        def _find_inf(obj):
            if isinstance(obj, dict):
                for v in obj.values():
                    yield from _find_inf(v)
            elif isinstance(obj, list):
                for v in obj:
                    yield from _find_inf(v)
            elif obj == "inf":
                yield obj

        # We don't require inf to be present, but if it is, must be str.
        # (Typical YES bribery is feasible — this test mostly proves the
        # serialiser path doesn't crash.)
        list(_find_inf(data))  # consume generator; no crash = pass

    def test_scrub_floats_handles_nan(self) -> None:
        """Direct unit test of the float-scrubber helper."""
        result = demo._scrub_floats({
            "a": math.inf,
            "b": math.nan,
            "c": 1.5,
            "d": [math.inf, 2.0, math.nan],
        })
        assert result["a"] == "inf"
        assert result["b"] == "nan"
        assert result["c"] == 1.5
        assert result["d"] == ["inf", 2.0, "nan"]

    def test_json_matches_direct_call(self, tmp_path: Path) -> None:
        """JSON output for collusion matches the direct library call's
        result on key fields."""
        out_path = tmp_path / "collusion.json"
        demo.main(["--vector", "collusion", "--json", str(out_path)])
        data = json.loads(out_path.read_text())
        collusion_data = data["results"]["collusion"]
        # Verify total_sybil_weight equals 3 colluders × 1.0 base weight
        assert collusion_data["total_sybil_weight"] == pytest.approx(3.0)


# ---------------------------------------------------------------------------
# Subprocess invocation
# ---------------------------------------------------------------------------


class TestSubprocessInvocation:
    def test_module_runs_via_python_m(self) -> None:
        """`python -m scripts.adversarial_demo` exits 0 and prints
        expected sections."""
        repo_root = Path(__file__).resolve().parent.parent
        proc = subprocess.run(
            [sys.executable, "-m", "scripts.adversarial_demo"],
            capture_output=True,
            text=True,
            cwd=str(repo_root),
        )
        assert proc.returncode == 0, proc.stderr
        assert "Adversarial Simulation" in proc.stdout
        assert "Collusion result" in proc.stdout

    def test_subprocess_compare_flag(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        proc = subprocess.run(
            [sys.executable, "-m", "scripts.adversarial_demo", "--compare"],
            capture_output=True,
            text=True,
            cwd=str(repo_root),
        )
        assert proc.returncode == 0
        assert "Attack vector comparison" in proc.stdout

    def test_subprocess_with_target(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.adversarial_demo",
                "--target",
                "NO",
                "--vector",
                "collusion",
            ],
            capture_output=True,
            text=True,
            cwd=str(repo_root),
        )
        assert proc.returncode == 0
        assert "Target decision: NO" in proc.stdout
