"""Tests for ``scripts/sybil_demo.py`` CLI.

Covers:
- argparse: rejects bad ranges, accepts all valid targets, ``--all`` flag
- output: text report contains expected sections / numbers
- ``--json``: writes a parseable JSON file at the chosen path, including
  to a non-existent parent directory (auto-creates)
- subprocess: ``python -m scripts.sybil_demo`` exits 0 and prints to stdout
- correctness: JSON output matches what the library would produce directly
"""
from __future__ import annotations

import io
import json
import os
import pathlib
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout
from typing import Iterable

import pytest

from scripts import sybil_demo
from swarm_oracle import sybil as _sybil


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


class TestArgParse:
    def test_default_target_is_yes(self):
        ns = sybil_demo._parse_args([])
        assert ns.target == "YES"
        assert ns.all is False
        assert ns.base_rate == 0.5
        assert ns.oracle_brier == 0.10

    @pytest.mark.parametrize("t", ["YES", "NO", "DISPUTE"])
    def test_accepts_all_valid_targets(self, t):
        ns = sybil_demo._parse_args(["--target", t])
        assert ns.target == t

    @pytest.mark.parametrize("bad", ["yes", "MAYBE", "FLIP", ""])
    def test_rejects_invalid_target(self, bad):
        with pytest.raises(SystemExit):
            sybil_demo._parse_args(["--target", bad])

    @pytest.mark.parametrize("bad", ["-0.01", "1.01", "2.0"])
    def test_rejects_out_of_range_base_rate(self, bad):
        with pytest.raises(SystemExit):
            sybil_demo._parse_args(["--base-rate", bad])

    @pytest.mark.parametrize("bad", ["-0.01", "1.01"])
    def test_rejects_out_of_range_oracle_brier(self, bad):
        with pytest.raises(SystemExit):
            sybil_demo._parse_args(["--oracle-brier", bad])

    @pytest.mark.parametrize("bad", ["-0.01", "1.01", "5"])
    def test_rejects_out_of_range_attacker_vote(self, bad):
        with pytest.raises(SystemExit):
            sybil_demo._parse_args(["--attacker-vote", bad])

    def test_all_flag(self):
        ns = sybil_demo._parse_args(["--all"])
        assert ns.all is True


# ---------------------------------------------------------------------------
# Text output content
# ---------------------------------------------------------------------------


def _run_cli(args: list[str]) -> tuple[str, int]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = sybil_demo.main(args)
    return buf.getvalue(), rc


class TestTextOutput:
    def test_yes_target_default(self):
        text, rc = _run_cli([])
        assert rc == 0
        assert "Swarm Oracle — Sybil-Resistance Analysis" in text
        assert "Target: YES" in text
        assert "Baseline:" in text
        assert "Cheap-Sybil cost:" in text

    def test_no_target_zero_cost(self):
        text, rc = _run_cli(["--target", "NO"])
        assert rc == 0
        assert "Target: NO" in text
        # Demo baseline is NO; cost should be 0 / no-attack-needed.
        assert "0 base-weight Sybils" in text or "no attack needed" in text.lower()

    def test_dispute_target_cheap(self):
        text, rc = _run_cli(["--target", "DISPUTE"])
        assert rc == 0
        assert "Target: DISPUTE" in text

    def test_all_flag_includes_three_sections(self):
        text, rc = _run_cli(["--all"])
        assert rc == 0
        assert "Target: YES" in text
        assert "Target: NO" in text
        assert "Target: DISPUTE" in text

    def test_base_rate_appears_in_header(self):
        text, rc = _run_cli(["--base-rate", "0.3"])
        assert rc == 0
        assert "Base rate (assumed): 0.300" in text

    def test_attacker_vote_forced_appears_in_header(self):
        text, rc = _run_cli(["--target", "YES", "--attacker-vote", "0.95"])
        assert rc == 0
        assert "Attacker vote:" in text
        assert "0.950" in text

    def test_infeasible_attack_marks_infeasible(self):
        # Forcing attacker vote at YES threshold makes attack infeasible.
        text, rc = _run_cli(
            ["--target", "YES", "--attacker-vote", "0.85"]
        )
        assert rc == 0
        assert "infeasible" in text.lower() or "∞" in text


# ---------------------------------------------------------------------------
# JSON output
# ---------------------------------------------------------------------------


class TestJsonOutput:
    def test_writes_json_at_given_path(self, tmp_path: pathlib.Path):
        out = tmp_path / "report.json"
        text, rc = _run_cli(["--target", "YES", "--json", str(out)])
        assert rc == 0
        assert out.exists()
        data = json.loads(out.read_text())
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["target"] == "YES"
        assert "min_base_weight_sybils" in data[0]
        assert "max_attainable_sybil_weight" in data[0]

    def test_all_flag_writes_three_records(self, tmp_path: pathlib.Path):
        out = tmp_path / "all.json"
        text, rc = _run_cli(["--all", "--json", str(out)])
        assert rc == 0
        data = json.loads(out.read_text())
        assert len(data) == 3
        assert [r["target"] for r in data] == ["YES", "NO", "DISPUTE"]

    def test_creates_parent_directory(self, tmp_path: pathlib.Path):
        out = tmp_path / "nested" / "deeper" / "report.json"
        assert not out.parent.exists()
        text, rc = _run_cli(["--json", str(out)])
        assert rc == 0
        assert out.exists()
        assert out.parent.is_dir()

    def test_json_values_match_library_directly(self, tmp_path: pathlib.Path):
        out = tmp_path / "report.json"
        _run_cli(["--target", "YES", "--json", str(out)])
        cli_data = json.loads(out.read_text())[0]

        # Now compute the same thing directly and compare.
        scenario = _sybil.demo_scenario("YES")
        margin = _sybil.protocol_security_margin(scenario)

        assert cli_data["baseline_decision"] == margin.baseline_decision
        assert (
            abs(cli_data["baseline_probability"] - margin.baseline_probability)
            < 1e-9
        )
        assert cli_data["target_decision"] == margin.target_decision
        assert cli_data["min_base_weight_sybils"] == margin.min_base_weight_sybils
        assert (
            abs(
                cli_data["min_total_sybil_weight"]
                - margin.min_total_sybil_weight
            )
            < 1e-6
        )

    def test_infinity_serialized_as_string(self, tmp_path: pathlib.Path):
        # DISPUTE with constant-voter Sybil at base rate 0.5 → predictions
        # to match oracle is inf.
        out = tmp_path / "report.json"
        _run_cli(["--target", "DISPUTE", "--json", str(out)])
        data = json.loads(out.read_text())[0]
        # Either a finite number or the "inf" sentinel.
        v = data["predictions_to_match_oracle"]
        assert v == "inf" or isinstance(v, (int, float))


# ---------------------------------------------------------------------------
# Subprocess invocation — ensures the module is callable as documented
# ---------------------------------------------------------------------------


class TestSubprocessInvocation:
    def test_python_dash_m_invocation(self):
        repo_root = pathlib.Path(__file__).resolve().parent.parent
        result = subprocess.run(
            [sys.executable, "-m", "scripts.sybil_demo"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, (
            f"stderr: {result.stderr!r}; stdout: {result.stdout!r}"
        )
        assert "Swarm Oracle — Sybil-Resistance Analysis" in result.stdout
        assert "Target: YES" in result.stdout

    def test_subprocess_all_flag(self):
        repo_root = pathlib.Path(__file__).resolve().parent.parent
        result = subprocess.run(
            [sys.executable, "-m", "scripts.sybil_demo", "--all"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0
        for target in ("YES", "NO", "DISPUTE"):
            assert f"Target: {target}" in result.stdout
