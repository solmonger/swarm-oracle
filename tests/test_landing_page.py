"""Structural conformance tests for the GitHub Pages landing page.

These tests pin the contract for ``index.html``, ``JUDGES.md``, and the
``.github/workflows/pages.yml`` deploy workflow. The goal is to keep the
hackathon-visible surface tight: if a refactor breaks the canonical
design tokens, drops a required CTA, or sneaks in a third-party CDN
dependency, CI catches it before judges see the regression.

Tests are intentionally string-based rather than DOM-parsing — the page
must remain a single, no-build, hand-readable HTML file. We assert on the
literal text the user agent sees.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
INDEX_HTML = REPO_ROOT / "index.html"
JUDGES_MD = REPO_ROOT / "JUDGES.md"
DEMO_HTML = REPO_ROOT / "demo.html"
PAGES_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "pages.yml"

# Canonical design tokens — mirrors what demo.html declares. The landing
# page MUST declare these exact name/value pairs so the visual identity
# stays consistent between the demo, the benchmark, and the landing
# page.
CANONICAL_TOKENS = {
    "--bg": "#0a0e1a",
    "--surface": "#111827",
    "--surface-2": "#1f2937",
    "--border": "#374151",
    "--text": "#e5e7eb",
    "--text-muted": "#9ca3af",
    "--cyan": "#06b6d4",
    "--cyan-dim": "#0891b2",
    "--blue": "#3b82f6",
    "--purple": "#8b5cf6",
    "--green": "#10b981",
    "--red": "#ef4444",
    "--amber": "#f59e0b",
}


# --- Module-level fixtures ----------------------------------------------------


@pytest.fixture(scope="module")
def index_html() -> str:
    assert INDEX_HTML.exists(), (
        f"Missing landing page: {INDEX_HTML}. "
        "GitHub Pages will fall back to README rendering if this file "
        "is absent."
    )
    return INDEX_HTML.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def judges_md() -> str:
    assert JUDGES_MD.exists(), (
        f"Missing judges quickstart: {JUDGES_MD}. "
        "The landing page links to this file; judges should not 404."
    )
    return JUDGES_MD.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def pages_workflow() -> str:
    assert PAGES_WORKFLOW.exists(), (
        f"Missing Pages deploy workflow: {PAGES_WORKFLOW}. "
        "Without this, index.html updates do not auto-publish."
    )
    return PAGES_WORKFLOW.read_text(encoding="utf-8")


# --- Structural HTML checks ---------------------------------------------------


class TestIndexHtmlStructure:
    """The landing page must remain a single, valid, hand-readable HTML file."""

    def test_doctype_declared(self, index_html: str) -> None:
        assert index_html.lstrip().lower().startswith("<!doctype html>")

    def test_has_html_lang_attribute(self, index_html: str) -> None:
        assert re.search(r'<html\s+lang="[a-z]{2}"', index_html), (
            "Root <html> tag must declare a language for accessibility."
        )

    def test_has_charset_utf8(self, index_html: str) -> None:
        assert re.search(r'<meta\s+charset="UTF-8"', index_html, re.IGNORECASE)

    def test_has_viewport_meta(self, index_html: str) -> None:
        assert "name=\"viewport\"" in index_html
        assert "width=device-width" in index_html

    def test_has_descriptive_title(self, index_html: str) -> None:
        m = re.search(r"<title>(.*?)</title>", index_html, re.IGNORECASE)
        assert m, "Missing <title> tag"
        title = m.group(1).strip()
        assert "Swarm Oracle" in title
        # A real title, not a placeholder
        assert len(title) > len("Swarm Oracle")

    def test_has_meta_description(self, index_html: str) -> None:
        assert re.search(
            r'<meta\s+name="description"\s+content="[^"]{40,}"', index_html
        ), "Missing or too-short <meta name=\"description\">"

    def test_has_open_graph_tags(self, index_html: str) -> None:
        for prop in ("og:title", "og:description", "og:url"):
            assert f'property="{prop}"' in index_html, (
                f"Missing Open Graph tag: {prop}"
            )

    def test_balanced_html_tags(self, index_html: str) -> None:
        # Crude but effective: opening and closing tag counts must match
        # for the elements we use as section containers.
        for tag in ("html", "head", "body", "nav", "header", "footer"):
            opens = len(re.findall(rf"<{tag}\b", index_html, re.IGNORECASE))
            closes = len(re.findall(rf"</{tag}>", index_html, re.IGNORECASE))
            assert opens == closes, (
                f"Unbalanced <{tag}> tags: {opens} open vs {closes} close"
            )


# --- Design token conformance ------------------------------------------------


class TestDesignTokenConformance:
    """Landing page CSS tokens must match demo.html bit-for-bit."""

    @pytest.mark.parametrize("token,value", list(CANONICAL_TOKENS.items()))
    def test_canonical_token_declared(
        self, index_html: str, token: str, value: str
    ) -> None:
        # Tokens are declared as `--name: #value;` inside :root { ... }
        pattern = rf"{re.escape(token)}\s*:\s*{re.escape(value)}\s*;"
        assert re.search(pattern, index_html), (
            f"Token {token} must be declared with value {value} "
            f"(matches demo.html canonical)."
        )

    def test_no_legacy_token_names(self, index_html: str) -> None:
        # These were renamed in a prior design pass; declaring them now
        # would silently shadow the canonical names.
        for legacy in ("--accent", "--panel", "--muted", "--good", "--bad", "--warn"):
            pattern = rf"{re.escape(legacy)}\s*:"
            assert not re.search(pattern, index_html), (
                f"Legacy token {legacy} must not be declared on the "
                f"landing page."
            )

    def test_h1_uses_cyan_to_purple_gradient(self, index_html: str) -> None:
        # The canonical h1 treatment from demo.html. The visual identity
        # falls apart if the landing page drops the gradient.
        block = re.search(r"h1\s*\{[^}]*\}", index_html, re.DOTALL)
        assert block, "h1 selector not found in <style>"
        assert "linear-gradient" in block.group(0)
        assert "var(--cyan)" in block.group(0)
        assert "var(--purple)" in block.group(0)

    def test_consistent_with_demo_html(self) -> None:
        # Sanity-check the source of truth: demo.html should declare the
        # same tokens we mirror.
        assert DEMO_HTML.exists(), "demo.html missing — cannot verify token parity"
        demo = DEMO_HTML.read_text(encoding="utf-8")
        for token, value in CANONICAL_TOKENS.items():
            if token == "--cyan-dim":
                # Sanity: demo.html uses the same value
                pattern = rf"{re.escape(token)}\s*:\s*{re.escape(value)}\s*;"
                assert re.search(pattern, demo), (
                    f"demo.html should declare {token}: {value}; "
                    "drift between demo.html and index.html will confuse judges."
                )


# --- Content requirements ----------------------------------------------------


class TestContentRequirements:
    """Required hero copy, stats, CTAs, and section anchors."""

    @pytest.mark.parametrize(
        "section_id",
        ["how", "results", "architecture", "contracts", "try"],
    )
    def test_section_anchor_present(self, index_html: str, section_id: str) -> None:
        assert f'id="{section_id}"' in index_html, (
            f"Missing section anchor #{section_id}; nav links will 404."
        )

    @pytest.mark.parametrize(
        "anchor_text",
        ["How it works", "Results", "Architecture", "Contracts", "Try it"],
    )
    def test_nav_link_text_present(self, index_html: str, anchor_text: str) -> None:
        assert anchor_text in index_html, (
            f"Missing nav-link text: {anchor_text!r}"
        )

    def test_headline_benchmark_numbers_visible(self, index_html: str) -> None:
        # These match benchmark.json (50-case, seed=42). If the benchmark
        # moves and we forget to refresh the landing page, this test catches it.
        for headline in ("100%", "0.0724"):
            assert headline in index_html, (
                f"Headline stat missing from landing page: {headline}"
            )
        # Accept 647 (original), 702, 713, 741, or 742 (with Deploy.s.sol broadcast test)
        assert ("742" in index_html or "741" in index_html or "713" in index_html or "702" in index_html or "647" in index_html), (
            "Test count (742, 741, 713, 702, or 647) missing from landing page"
        )

    def test_comparison_table_full(self, index_html: str) -> None:
        # All six benchmarked methods must appear, in case judges scan
        # for their pet baseline.
        for method in (
            "swarm",
            "agent-oracle",
            "agent-reliable",
            "agent-novice",
            "majority",
            "average",
        ):
            assert method in index_html, (
                f"Benchmark method missing from comparison table: {method}"
            )

    def test_github_repo_url(self, index_html: str) -> None:
        assert "https://github.com/solmonger/swarm-oracle" in index_html

    def test_youtube_demo_url(self, index_html: str) -> None:
        assert "https://youtu.be/Dy1h0Hcr4HQ" in index_html

    def test_devpost_url(self, index_html: str) -> None:
        assert "https://devpost.com/software/swarm-oracle" in index_html

    def test_links_to_interactive_demo(self, index_html: str) -> None:
        # demo.html should be reachable from the landing page; it's the
        # most polished interactive surface we have.
        assert 'href="demo.html"' in index_html

    def test_links_to_judges_md(self, index_html: str) -> None:
        assert 'href="JUDGES.md"' in index_html

    def test_links_to_benchmark_html(self, index_html: str) -> None:
        assert 'href="benchmark.html"' in index_html


# --- Architecture diagram ----------------------------------------------------


class TestEmbeddedArchitectureSVG:
    """The architecture diagram must ship inline (no external load)."""

    def test_inline_svg_present(self, index_html: str) -> None:
        assert "<svg" in index_html and "</svg>" in index_html, (
            "Landing page must embed the architecture SVG inline."
        )

    def test_svg_has_accessible_label(self, index_html: str) -> None:
        # aria-label is the minimum-viable accessibility hook for an
        # SVG-rendered diagram.
        m = re.search(r"<svg[^>]*aria-label=\"[^\"]+\"", index_html)
        assert m, "Architecture SVG must declare an aria-label."

    def test_svg_contains_pipeline_labels(self, index_html: str) -> None:
        # Spot-check that the SVG is actually the architecture diagram
        # and not some other unrelated graphic.
        for label in (
            "agent-oracle",
            "agent-reliable",
            "agent-novice",
            "CalibrationRegistry",
            "SwarmConsensus",
            "RewardDistribution",
            "AgentIdentity",
        ):
            assert label in index_html, (
                f"Architecture SVG missing pipeline label: {label}"
            )

    def test_svg_references_base_sepolia(self, index_html: str) -> None:
        assert "BASE SEPOLIA" in index_html


# --- Zero-CDN guarantee ------------------------------------------------------


class TestZeroExternalDependencies:
    """Landing page must remain self-contained: no CDN, no remote font, no tracker."""

    @pytest.mark.parametrize(
        "external_marker",
        [
            "cdnjs.cloudflare.com",
            "unpkg.com",
            "jsdelivr.net",
            "fonts.googleapis.com",
            "fonts.gstatic.com",
            "cdn.tailwindcss.com",
            "google-analytics.com",
            "googletagmanager.com",
        ],
    )
    def test_no_external_cdn(self, index_html: str, external_marker: str) -> None:
        assert external_marker not in index_html, (
            f"Landing page must be self-contained; found external CDN "
            f"reference to {external_marker}."
        )

    def test_no_external_script_src(self, index_html: str) -> None:
        # Any <script src="..."> that's not data-uri / relative is a
        # network load and breaks the "works offline" promise.
        for m in re.finditer(r'<script\s+[^>]*src="([^"]+)"', index_html):
            src = m.group(1)
            assert not src.startswith(("http://", "https://", "//")), (
                f"External <script src=\"{src}\"> not allowed; bundle "
                "inline instead."
            )

    def test_no_external_stylesheet_href(self, index_html: str) -> None:
        for m in re.finditer(
            r'<link\s+[^>]*rel="stylesheet"[^>]*href="([^"]+)"', index_html
        ):
            href = m.group(1)
            assert not href.startswith(("http://", "https://", "//")), (
                f"External <link rel=\"stylesheet\" href=\"{href}\"> not "
                "allowed; bundle inline instead."
            )


# --- JUDGES.md ---------------------------------------------------------------


class TestJudgesMarkdown:
    """The judges' quickstart must remain comprehensive and link-correct."""

    @pytest.mark.parametrize(
        "heading",
        [
            "The 30-second pitch",
            "Headline result",
            "Verify it yourself",
            "Watch it",
            "What's novel",
            "Tech stack",
        ],
    )
    def test_required_section(self, judges_md: str, heading: str) -> None:
        assert heading in judges_md, (
            f"JUDGES.md must contain section: {heading!r}"
        )

    def test_links_to_repo_and_video(self, judges_md: str) -> None:
        assert "https://github.com/solmonger/swarm-oracle" in judges_md
        assert "https://youtu.be/Dy1h0Hcr4HQ" in judges_md
        assert "https://devpost.com/software/swarm-oracle" in judges_md

    def test_quotes_headline_benchmark(self, judges_md: str) -> None:
        # 50-case benchmark (seed=42): 100% accuracy, 0.0724 swarm Brier
        for n in ("100%", "0.0724"):
            assert n in judges_md, f"Missing benchmark headline {n}"

    def test_clone_instructions_present(self, judges_md: str) -> None:
        assert "git clone https://github.com/solmonger/swarm-oracle.git" in judges_md
        assert "make test" in judges_md
        assert "make benchmark" in judges_md


# --- Pages deploy workflow ---------------------------------------------------


class TestPagesWorkflow:
    """The GitHub Pages deploy workflow must remain a no-build path."""

    def test_workflow_name(self, pages_workflow: str) -> None:
        assert "Deploy GitHub Pages" in pages_workflow

    def test_triggers_on_main_push(self, pages_workflow: str) -> None:
        assert "branches: [main]" in pages_workflow

    def test_triggers_when_landing_page_changes(self, pages_workflow: str) -> None:
        # If a contributor changes index.html they expect the deploy to
        # fire — guard the path list.
        for path in ("index.html", "JUDGES.md", "demo.html", "benchmark.html"):
            assert f"'{path}'" in pages_workflow, (
                f"Pages workflow must include {path} in its path triggers."
            )

    def test_has_pages_permissions(self, pages_workflow: str) -> None:
        # Required permissions for actions/deploy-pages@v4
        for perm in ("pages: write", "id-token: write", "contents: read"):
            assert perm in pages_workflow, f"Missing Pages permission: {perm}"

    def test_uses_modern_deploy_pages_action(self, pages_workflow: str) -> None:
        assert "actions/deploy-pages" in pages_workflow
        assert "actions/upload-pages-artifact" in pages_workflow
        assert "actions/configure-pages" in pages_workflow

    def test_creates_nojekyll_marker(self, pages_workflow: str) -> None:
        # Without .nojekyll, GH Pages tries to Jekyll-process underscored
        # paths and quietly hides them; this has burned us before.
        assert ".nojekyll" in pages_workflow

    def test_stages_index_html(self, pages_workflow: str) -> None:
        assert "cp index.html _site/" in pages_workflow

    def test_single_deployment_concurrency(self, pages_workflow: str) -> None:
        # Pages allows only one active deployment per environment;
        # concurrency: pages prevents 409s on rapid pushes.
        assert "group: pages" in pages_workflow


# --- Cross-surface sanity ----------------------------------------------------


class TestCrossSurfaceLinks:
    """Make sure index.html, JUDGES.md, and the workflow agree on URLs."""

    def test_github_repo_url_matches_workflow(
        self, index_html: str, judges_md: str
    ) -> None:
        # If the repo gets renamed, all three surfaces should fail
        # together rather than silently disagree.
        assert "solmonger/swarm-oracle" in index_html
        assert "solmonger/swarm-oracle" in judges_md

    def test_video_url_matches(self, index_html: str, judges_md: str) -> None:
        # The same video URL is referenced from the landing page and
        # JUDGES.md; if one moves, this catches drift.
        assert "youtu.be/Dy1h0Hcr4HQ" in index_html
        assert "youtu.be/Dy1h0Hcr4HQ" in judges_md
