"""Tests that the repo ships the open-source contribution norms.

Specifically:
- CONTRIBUTING.md exists with required sections (Quick start, Tests,
  Style and architecture, PR flow, Reporting security issues).
- SECURITY.md exists with required sections (Reporting a vulnerability,
  Scope, What you'll get back).
- README.md links to both files.
- docs/security-model.md exists, has section headers, and references the
  sybil module.
- Makefile exposes the sybil-demo and test-sybil targets.
"""
from __future__ import annotations

import pathlib
import re

import pytest


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def _read(rel: str) -> str:
    return (REPO_ROOT / rel).read_text()


# ---------------------------------------------------------------------------
# CONTRIBUTING.md
# ---------------------------------------------------------------------------


class TestContributing:
    def test_file_exists(self):
        assert (REPO_ROOT / "CONTRIBUTING.md").is_file()

    @pytest.mark.parametrize(
        "section",
        [
            "## Quick start",
            "## Where the code lives",
            "## Tests are the contract",
            "## Style and architecture",
            "## PR flow",
            "## Reporting security issues",
        ],
    )
    def test_has_required_section(self, section):
        content = _read("CONTRIBUTING.md")
        assert section in content, f"missing section: {section}"

    def test_mentions_pytest_command(self):
        content = _read("CONTRIBUTING.md")
        assert "python -m pytest" in content

    def test_mentions_forge_test_command(self):
        content = _read("CONTRIBUTING.md")
        assert "forge test" in content

    def test_links_to_security(self):
        content = _read("CONTRIBUTING.md")
        assert "SECURITY.md" in content


# ---------------------------------------------------------------------------
# SECURITY.md
# ---------------------------------------------------------------------------


class TestSecurity:
    def test_file_exists(self):
        assert (REPO_ROOT / "SECURITY.md").is_file()

    @pytest.mark.parametrize(
        "section",
        [
            "## Reporting a vulnerability",
            "## Scope",
            "## What you'll get back",
            "## Disclosure history",
        ],
    )
    def test_has_required_section(self, section):
        content = _read("SECURITY.md")
        assert section in content, f"missing section: {section}"

    def test_contact_email_present(self):
        content = _read("SECURITY.md")
        # Look for any email-like string in the file.
        assert re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", content), (
            "expected an email address in SECURITY.md"
        )

    def test_acknowledge_timeline_present(self):
        content = _read("SECURITY.md").lower()
        # Either explicit hours/days for acknowledgement.
        assert "48 hours" in content or "7 days" in content

    def test_references_sybil_analysis(self):
        # The Sybil cost is one of the explicit in-scope items.
        content = _read("SECURITY.md")
        assert "Sybil" in content
        assert "docs/security-model.md" in content


# ---------------------------------------------------------------------------
# README.md — linking + Security Model section
# ---------------------------------------------------------------------------


class TestReadmeLinksAndSections:
    def test_security_model_section_present(self):
        content = _read("README.md")
        assert "## Security Model" in content

    def test_contributing_section_present(self):
        content = _read("README.md")
        assert "## Contributing" in content

    def test_links_to_contributing(self):
        content = _read("README.md")
        assert "CONTRIBUTING.md" in content

    def test_links_to_security(self):
        content = _read("README.md")
        assert "SECURITY.md" in content

    def test_links_to_security_model_doc(self):
        content = _read("README.md")
        assert "docs/security-model.md" in content

    def test_mentions_272_sybils(self):
        # Headline number; if the math changes we want this test to scream.
        content = _read("README.md")
        assert "272" in content

    def test_mentions_make_sybil_demo(self):
        content = _read("README.md")
        assert "make sybil-demo" in content


# ---------------------------------------------------------------------------
# docs/security-model.md
# ---------------------------------------------------------------------------


class TestSecurityModelDoc:
    def test_file_exists(self):
        assert (REPO_ROOT / "docs" / "security-model.md").is_file()

    @pytest.mark.parametrize(
        "section",
        [
            "## TL;DR",
            "## Notation",
            "## 1. The Mean-Crossing Lower Bound",
            "## 2. The Variance Gate",
            "## 3. The Calibration Ceiling",
            "## 4. The Dispute Surface",
            "## 5. The Combined Picture",
            "## 6. Reproducing the Numbers",
            "## 7. Limitations and Future Work",
        ],
    )
    def test_section_present(self, section):
        content = _read("docs/security-model.md")
        assert section in content, f"missing section: {section}"

    def test_references_sybil_module(self):
        content = _read("docs/security-model.md")
        assert "swarm_oracle/sybil.py" in content

    def test_references_test_suite(self):
        content = _read("docs/security-model.md")
        assert "tests/test_sybil.py" in content

    @pytest.mark.parametrize(
        "headline",
        [
            "272",  # cheap-sybil cost
            "3.984",  # constant-voter ceiling at r=0.5
            "0.25",  # min Brier at r=0.5
        ],
    )
    def test_headline_numbers_match(self, headline):
        content = _read("docs/security-model.md")
        assert headline in content, f"expected headline number {headline}"


# ---------------------------------------------------------------------------
# Makefile targets
# ---------------------------------------------------------------------------


class TestMakefileTargets:
    @pytest.mark.parametrize(
        "target",
        [
            "test-sybil:",
            "sybil-demo:",
            "sybil-demo-all:",
            "test-adversarial:",
            "adversarial-demo:",
            "adversarial-compare:",
            "adversarial-demo-all:",
        ],
    )
    def test_target_present(self, target):
        content = _read("Makefile")
        assert target in content, f"missing Makefile target: {target}"

    def test_phony_declaration_lists_new_targets(self):
        content = _read("Makefile")
        # All Sybil + adversarial targets should be in the .PHONY list.
        phony_line = [
            line for line in content.splitlines() if line.startswith(".PHONY:")
        ]
        assert phony_line, "Makefile has no .PHONY declaration"
        joined = " ".join(phony_line)
        for t in (
            "test-sybil",
            "sybil-demo",
            "sybil-demo-all",
            "test-adversarial",
            "adversarial-demo",
            "adversarial-compare",
            "adversarial-demo-all",
        ):
            assert t in joined, f".PHONY missing {t}"


# ---------------------------------------------------------------------------
# docs/threat-model.md (multi-vector adversarial analysis)
# ---------------------------------------------------------------------------


class TestThreatModelDoc:
    def test_file_exists(self):
        assert (REPO_ROOT / "docs" / "threat-model.md").is_file()

    @pytest.mark.parametrize(
        "section",
        [
            "## TL;DR",
            "## Notation",
            "## §1. Collusion",
            "## §2. Adaptive attacker",
            "## §3. Bribery",
            "## §4. Combined vector",
            "## §5. Out of scope",
            "## §6. Reproducing the numbers",
            "## §7. Limitations",
        ],
    )
    def test_section_present(self, section):
        content = _read("docs/threat-model.md")
        assert section in content, f"missing threat-model section: {section}"

    def test_references_adversarial_module(self):
        content = _read("docs/threat-model.md")
        assert "swarm_oracle/adversarial.py" in content
        assert "tests/test_adversarial.py" in content

    def test_references_demo_commands(self):
        content = _read("docs/threat-model.md")
        assert "make adversarial-demo" in content
        assert "make adversarial-compare" in content


# ---------------------------------------------------------------------------
# docs/competitive-comparison.md
# ---------------------------------------------------------------------------


class TestCompetitiveComparisonDoc:
    def test_file_exists(self):
        assert (REPO_ROOT / "docs" / "competitive-comparison.md").is_file()

    @pytest.mark.parametrize(
        "competitor",
        ["UMA", "Augur", "Reality.eth", "Chainlink", "Pyth"],
    )
    def test_competitor_present(self, competitor):
        content = _read("docs/competitive-comparison.md")
        assert competitor in content, (
            f"missing competitor coverage: {competitor}"
        )

    @pytest.mark.parametrize(
        "section",
        [
            "## TL;DR matrix",
            "## §1. UMA",
            "## §2. Augur v2",
            "## §3. Reality.eth",
            "## §4. Chainlink",
            "## §5. Pyth",
            "## §7. Positioning statement",
        ],
    )
    def test_section_present(self, section):
        content = _read("docs/competitive-comparison.md")
        assert section in content, (
            f"missing competitive-comparison section: {section}"
        )


# ---------------------------------------------------------------------------
# README references the new docs
# ---------------------------------------------------------------------------


class TestReadmeAdversarialReferences:
    def test_threat_model_link(self):
        content = _read("README.md")
        assert "docs/threat-model.md" in content

    def test_competitive_comparison_link(self):
        content = _read("README.md")
        assert "docs/competitive-comparison.md" in content

    def test_adversarial_test_count_mentioned(self):
        content = _read("README.md")
        # Headline test counts: 59 + 31 = 90 new tests
        assert "59 tests" in content
        assert "31 tests" in content
