"""
tests/test_notebook.py — Verify the Jupyter notebook is well-formed and
covers all required protocol sections.

Run:  python -m pytest tests/test_notebook.py -v
"""
import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
NOTEBOOK_PATH = REPO_ROOT / "notebooks" / "swarm_oracle_demo.ipynb"


# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────

def load_notebook():
    """Parse the notebook once; all tests use this fixture."""
    with open(NOTEBOOK_PATH) as f:
        return json.load(f)


def get_all_source(nb, cell_type=None):
    """Return concatenated source text across all (matching) cells."""
    parts = []
    for cell in nb["cells"]:
        if cell_type is None or cell["cell_type"] == cell_type:
            src = cell.get("source", "")
            if isinstance(src, list):
                src = "".join(src)
            parts.append(src)
    return "\n".join(parts)


# ─────────────────────────────────────────────────────────────────
# 1. Existence and format
# ─────────────────────────────────────────────────────────────────

class TestNotebookExists:
    def test_file_present(self):
        assert NOTEBOOK_PATH.exists(), (
            f"notebooks/swarm_oracle_demo.ipynb not found at {NOTEBOOK_PATH}"
        )

    def test_valid_json(self):
        nb = load_notebook()
        assert isinstance(nb, dict)

    def test_nbformat_version(self):
        nb = load_notebook()
        assert nb.get("nbformat") >= 4, "Notebook must be nbformat 4+"

    def test_has_cells(self):
        nb = load_notebook()
        assert len(nb.get("cells", [])) >= 10, (
            "Notebook should have at least 10 cells"
        )

    def test_has_kernel_metadata(self):
        nb = load_notebook()
        assert "metadata" in nb
        assert "kernelspec" in nb["metadata"]

    def test_language_is_python(self):
        nb = load_notebook()
        lang = (
            nb["metadata"]
            .get("kernelspec", {})
            .get("language", "")
        )
        assert lang == "python"


# ─────────────────────────────────────────────────────────────────
# 2. Cell type distribution
# ─────────────────────────────────────────────────────────────────

class TestCellStructure:
    def test_has_markdown_cells(self):
        nb = load_notebook()
        md_cells = [c for c in nb["cells"] if c["cell_type"] == "markdown"]
        assert len(md_cells) >= 5, "Need at least 5 markdown cells for narrative"

    def test_has_code_cells(self):
        nb = load_notebook()
        code_cells = [c for c in nb["cells"] if c["cell_type"] == "code"]
        assert len(code_cells) >= 8, "Need at least 8 code cells for demos"

    def test_first_cell_is_markdown(self):
        nb = load_notebook()
        assert nb["cells"][0]["cell_type"] == "markdown", (
            "First cell should be a markdown introduction"
        )

    def test_no_empty_cells(self):
        nb = load_notebook()
        for i, cell in enumerate(nb["cells"]):
            src = cell.get("source", "")
            if isinstance(src, list):
                src = "".join(src)
            assert src.strip(), f"Cell {i} is empty"


# ─────────────────────────────────────────────────────────────────
# 3. Required protocol sections (markdown headings)
# ─────────────────────────────────────────────────────────────────

REQUIRED_HEADINGS = [
    "Calibration",    # Part 1: calibration weights
    "Consensus",      # Part 2: consensus formation
    "Benchmark",      # Part 3: benchmark
    "Adversarial",    # Part 4: adversarial analysis
    "Economic",       # Part 5: economic security
    "On-Chain",       # Part 6: contracts
    "Summary",        # Final summary
]


class TestRequiredSections:
    @pytest.mark.parametrize("heading", REQUIRED_HEADINGS)
    def test_section_present(self, heading):
        nb = load_notebook()
        md_source = get_all_source(nb, cell_type="markdown")
        assert heading in md_source, (
            f"Notebook missing section containing '{heading}'"
        )

    def test_has_ci_badge(self):
        nb = load_notebook()
        first_cell = "".join(nb["cells"][0].get("source", ""))
        assert "CI" in first_cell and "badge" in first_cell.lower(), (
            "First cell should include the CI badge"
        )

    def test_has_title_heading(self):
        nb = load_notebook()
        first_cell = "".join(nb["cells"][0].get("source", ""))
        assert first_cell.strip().startswith("#"), (
            "First markdown cell should be an H1 heading"
        )
        assert "Swarm Oracle" in first_cell


# ─────────────────────────────────────────────────────────────────
# 4. Key protocol claims are documented
# ─────────────────────────────────────────────────────────────────

REQUIRED_CODE_PATTERNS = [
    "compute_weight",         # calibration weight formula
    "weighted_consensus",     # consensus function
    "benchmark.json",         # benchmark results
    "brier",                  # Brier score mentioned
    "DISPUTE",                # variance-gate abstention
    "adversarial",            # adversarial analysis
    "economic_model",         # economic security
    "CalibrationRegistry",    # on-chain contract
    "forge test",             # Foundry test command
    "pytest",                 # Python test suite
]


class TestKeyClaimsCovered:
    @pytest.mark.parametrize("pattern", REQUIRED_CODE_PATTERNS)
    def test_pattern_present(self, pattern):
        nb = load_notebook()
        all_source = get_all_source(nb)
        assert pattern in all_source, (
            f"Notebook should mention '{pattern}' (required for completeness)"
        )

    def test_brier_formula_present(self):
        """LaTeX Brier score formula must appear in a markdown cell."""
        nb = load_notebook()
        md_source = get_all_source(nb, cell_type="markdown")
        assert "brier" in md_source.lower() or "B = " in md_source, (
            "Brier formula should appear in a markdown cell"
        )

    def test_swarm_beats_oracle_claim(self):
        """Notebook must make the headline benchmark claim."""
        nb = load_notebook()
        all_source = get_all_source(nb)
        # Accept "0.0724" or "beats" in context with "oracle"
        has_number = "0.0724" in all_source or "0.1029" in all_source
        has_beats = (
            "beats" in all_source.lower() or
            "better than" in all_source.lower()
        )
        assert has_number or has_beats, (
            "Notebook must state the headline result: swarm beats all agents"
        )

    def test_n_times_b_formula(self):
        """Economic security formula N × B > M must appear."""
        nb = load_notebook()
        all_source = get_all_source(nb)
        assert "N × B" in all_source or "N x B" in all_source or "N×B" in all_source, (
            "Economic model formula N × B > M should appear in notebook"
        )

    def test_test_counts_mentioned(self):
        """Test counts (600+) must be referenced somewhere."""
        nb = load_notebook()
        all_source = get_all_source(nb)
        counts = [int(m) for m in re.findall(r"\b(\d{3,})\b", all_source)]
        assert any(c >= 600 for c in counts), (
            "Notebook should reference the 600+ test count"
        )


# ─────────────────────────────────────────────────────────────────
# 5. Code quality
# ─────────────────────────────────────────────────────────────────

class TestCodeQuality:
    def test_no_raw_tracebacks(self):
        """Cells should not have Traceback output saved."""
        nb = load_notebook()
        for cell in nb["cells"]:
            outputs = cell.get("outputs", [])
            for out in outputs:
                assert out.get("output_type") != "error", (
                    "Notebook has saved error output — clear outputs before committing"
                )

    def test_imports_are_guarded(self):
        """Optional imports (matplotlib) should use try/except."""
        nb = load_notebook()
        code_source = get_all_source(nb, cell_type="code")
        if "matplotlib" in code_source:
            assert "try" in code_source and "ImportError" in code_source, (
                "matplotlib import should be guarded with try/except ImportError"
            )

    def test_llm_not_required(self):
        """Notebook must not hard-require a live LLM server."""
        nb = load_notebook()
        code_source = get_all_source(nb, cell_type="code")
        # Should not call swarm_verify or agent.py directly with real HTTP
        assert "requests.get" not in code_source, (
            "Notebook should not make raw HTTP calls requiring a live LLM"
        )

    def test_repo_root_detection(self):
        """Notebook should auto-detect repo root, not hardcode paths."""
        nb = load_notebook()
        code_source = get_all_source(nb, cell_type="code")
        assert "repo_root" in code_source, (
            "Notebook should compute repo_root dynamically"
        )
        # Should NOT hardcode /Users/operator
        assert "/Users/operator" not in code_source
        assert "/home/" not in code_source

    def test_no_hardcoded_secrets(self):
        """Notebook should not contain API keys or private keys."""
        nb = load_notebook()
        all_source = get_all_source(nb)
        BAD_PATTERNS = [
            r"sk-[A-Za-z0-9]{20,}",     # OpenAI key
            r"0x[0-9a-fA-F]{64}",        # private key (64 hex chars)
            r"Bearer [A-Za-z0-9]{20,}",  # auth token
        ]
        for pattern in BAD_PATTERNS:
            assert not re.search(pattern, all_source), (
                f"Notebook may contain a secret matching pattern {pattern}"
            )


# ─────────────────────────────────────────────────────────────────
# 6. Public surface
# ─────────────────────────────────────────────────────────────────

class TestPublicSurface:
    def test_notebook_in_notebooks_dir(self):
        assert NOTEBOOK_PATH.parent.name == "notebooks"

    def test_notebook_filename(self):
        assert NOTEBOOK_PATH.name == "swarm_oracle_demo.ipynb"

    def test_can_parse_all_json_source(self):
        """Every cell's source field must be valid (list-of-str or str)."""
        nb = load_notebook()
        for i, cell in enumerate(nb["cells"]):
            src = cell.get("source", "")
            assert isinstance(src, (str, list)), (
                f"Cell {i} source is neither str nor list: {type(src)}"
            )
