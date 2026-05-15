# Swarm Oracle — Design System

This document is the single source of truth for all UI and front-end work on
the Swarm Oracle project. Every HTML file, every new component, every color
decision must reference this file first.

---

## 1. Color Tokens

Defined as CSS custom properties on `:root`. Use token names — never raw hex
values — in any new HTML or CSS.

| Token | Value | Purpose |
|---|---|---|
| `--bg` | `#0a0e1a` | Page background (near-black blue) |
| `--surface` | `#111827` | Card / panel backgrounds |
| `--surface-2` | `#1f2937` | Elevated surfaces, hover states |
| `--border` | `#374151` | Dividers, card outlines |
| `--text` | `#e5e7eb` | Primary body text |
| `--text-muted` | `#9ca3af` | Secondary labels, captions |
| `--cyan` | `#06b6d4` | Primary brand accent (links, highlights, focus rings) |
| `--cyan-dim` | `#0891b2` | Hover / pressed state for cyan elements |
| `--blue` | `#3b82f6` | Informational, blockchain / on-chain indicators |
| `--purple` | `#8b5cf6` | Secondary accent (gradient partner to cyan) |
| `--green` | `#10b981` | YES / success / passing state |
| `--red` | `#ef4444` | NO / error / failing state |
| `--amber` | `#f59e0b` | DISPUTE / warning state |

### Decision Palette

The three decision outcomes map directly to color tokens:

```
YES     → --green  (#10b981)
NO      → --red    (#ef4444)
DISPUTE → --amber  (#f59e0b)
```

Never invent new outcome colors. These three are the protocol's visual language.

### Gradient

The brand gradient flows cyan → purple:

```css
background: linear-gradient(135deg, var(--cyan), var(--purple));
```

Use it for: `h1`, `.nav-brand`, stat value highlights, CTA button fills.

---

## 2. Typography

```css
--font-mono: 'SF Mono', 'Fira Code', 'JetBrains Mono', monospace;
--font-sans: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
```

**Rule:** `body` uses `--font-mono`. The terminal-aesthetic identity of the
project depends on this. Only use `--font-sans` for marketing copy (taglines,
hero subtitles, `section-lead` paragraphs) where readability matters more than
identity.

### Type Scale

| Element | Size | Weight | Notes |
|---|---|---|---|
| `h1` (hero) | `clamp(2rem, 5vw, 3.4rem)` | 700 | Gradient fill |
| `h2` (section) | `1.5rem` | 700 | Cyan left-border optional |
| `h3` (card title) | `1rem` | 600 | |
| Body | `0.9–1rem` | 400 | `--font-mono` |
| Caption / muted | `0.8–0.85rem` | 400 | `--text-muted` |
| Terminal text | `0.85rem` | 400 | `--font-mono`, inside `.terminal` |
| Nav links | `0.85rem` | 400 | `--text-muted`, hover `--cyan` |
| Stat values | `2rem` | 700 | Gradient fill |

---

## 3. Layout

### Containers

```css
.container      { max-width: 1100px; margin: 0 auto; padding: 2rem 1.5rem; }
.container-wide { max-width: 1280px; margin: 0 auto; padding: 0 1.5rem; }
```

Always wrap page-level content in `.container`. Use `.container-wide` only for
the sticky nav.

### Sections

Every content section:

```css
section { padding: 3rem 0; border-bottom: 1px solid var(--border); }
```

Each section gets an `id` for anchor navigation. Section IDs in use:
`how`, `results`, `architecture`, `contracts`, `try`.

### Grids

**Stats (headline numbers):**
```css
.headline-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 1rem; }
```

**Why cards (feature pillars):**
```css
.why-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 1rem; }
```

**Contract cards:**
```css
.contract-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 1rem; }
```

---

## 4. Core Components

### `.terminal`

The terminal block is the hero component. It should look like a macOS terminal.

```html
<div class="terminal">
  <div class="terminal-bar">
    <span class="term-dot dot-r"></span>
    <span class="term-dot dot-y"></span>
    <span class="term-dot dot-g"></span>
  </div>
  <pre class="terminal-body"><code>...</code></pre>
</div>
```

```css
.terminal {
  background: #0d1117;
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
}
.terminal-bar {
  display: flex; gap: 6px; padding: 10px 14px;
  background: #161b22;
  border-bottom: 1px solid var(--border);
}
.term-dot { width: 12px; height: 12px; border-radius: 50%; }
.dot-r { background: #ff5f57; }
.dot-y { background: #febc2e; }
.dot-g { background: #28c840; }
```

Syntax highlight classes available inside `<pre>`:

| Class | Color | Use for |
|---|---|---|
| `.py` | `--cyan` | Python keywords / filenames |
| `.sol` | `--purple` | Solidity / contract identifiers |
| `.num` | `--green` | Numbers, probabilities |
| `.accent` | `--amber` | Warnings, DISPUTE strings |

### `.stat-card`

Key metric display. Used in the headline stats row.

```html
<div class="stat-card">
  <div class="stat-value">541</div>
  <div class="stat-label">Python tests</div>
  <div class="stat-sub">passing, 3 skipped</div>
</div>
```

```css
.stat-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 1.5rem;
  text-align: center;
}
.stat-value { font-size: 2rem; font-weight: 700; /* gradient fill */ }
.stat-label { color: var(--text-muted); font-size: 0.85rem; margin-top: 0.25rem; }
.stat-sub   { color: var(--text-muted); font-size: 0.75rem; margin-top: 0.15rem; }
```

### `.why-card`

Feature explanation card. Three or four per row.

```html
<div class="why-card">
  <h3>Calibration-weighted</h3>
  <p>Agents earn influence through accuracy, not stake...</p>
</div>
```

```css
.why-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 1.5rem;
}
.why-card h3 { color: var(--cyan); margin-bottom: 0.5rem; }
```

### `.contract-card`

On-chain contract summary. One card per deployed contract.

```html
<div class="contract-card">
  <div class="contract-name">CalibrationRegistry.sol</div>
  <div class="contract-desc">Brier score storage + WAD weight computation</div>
  <div class="contract-addr"><a href="...basescan link..." target="_blank" rel="noopener noreferrer">0xABCD...1234</a></div>
</div>
```

```css
.contract-card {
  background: var(--surface);
  border: 1px solid var(--blue);
  border-radius: 8px;
  padding: 1.25rem;
}
.contract-name { color: var(--blue); font-weight: 600; margin-bottom: 0.3rem; }
.contract-addr a { color: var(--cyan); font-size: 0.8rem; }
```

**Rule:** Contract cards get `--blue` border to signal "on-chain". Python-side
cards get `--cyan` border.

### `.btn-primary` / `.btn-ghost`

```css
.btn {
  display: inline-block;
  padding: 0.65rem 1.4rem;
  border-radius: 6px;
  font-family: var(--font-mono);
  font-size: 0.9rem;
  text-decoration: none;
  cursor: pointer;
  transition: opacity 0.15s, background 0.15s;
}
.btn-primary {
  background: linear-gradient(135deg, var(--cyan), var(--purple));
  color: #fff;
  border: none;
}
.btn-primary:hover { opacity: 0.88; }
.btn-ghost {
  background: transparent;
  border: 1px solid var(--border);
  color: var(--text);
}
.btn-ghost:hover { background: var(--surface-2); border-color: var(--cyan); }
```

### `.compare-table`

Side-by-side comparison table for benchmark results or competitive matrix.

```css
.compare-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
}
.compare-table th {
  background: var(--surface-2);
  color: var(--cyan);
  padding: 0.6rem 0.8rem;
  text-align: left;
  border-bottom: 1px solid var(--border);
}
.compare-table td {
  padding: 0.55rem 0.8rem;
  border-bottom: 1px solid var(--border);
}
.compare-table tr:hover td { background: var(--surface-2); }
```

---

## 5. Navigation

Sticky top nav, backdrop-blur, mono brand name.

```html
<nav>
  <div class="container-wide nav-row">
    <span class="nav-brand">SWARM ORACLE</span>
    <div class="nav-links">
      <a href="#how">How it works</a>
      <a href="#results">Results</a>
      <a href="#architecture">Architecture</a>
      <a href="#contracts">On-chain</a>
      <a href="#try">Try it</a>
      <a href="https://github.com/SolMonger/swarm-oracle" target="_blank" rel="noopener noreferrer">GitHub ↗</a>
    </div>
  </div>
</nav>
```

Nav anchors must match section `id` attributes exactly.

---

## 6. Spacing Scale

All spacing uses `rem` multiples of 0.25.

| Use | Value |
|---|---|
| Card padding | `1.25–1.5rem` |
| Section padding | `3rem 0` |
| Grid gap | `1rem` (cards), `1.5rem` (sections) |
| Card border-radius | `8px` |
| Button border-radius | `6px` |
| Terminal border-radius | `8px` |

---

## 7. Accessibility Rules

- All interactive elements must have `:focus-visible` outlines: `outline: 2px solid var(--cyan); outline-offset: 2px; border-radius: 4px;`
- Color is never the sole differentiator (YES/NO/DISPUTE also use text labels)
- `<pre>` / terminal blocks use `role="region" aria-label="terminal output"` when they contain live data
- Minimum contrast: `--text` on `--bg` is 12.6:1 (AAA); `--cyan` on `--bg` is 4.9:1 (AA)
- All `<a>` links opening in new tabs include `target="_blank" rel="noopener noreferrer"`

---

## 8. File Map

| File | Purpose |
|---|---|
| `index.html` | Public landing page (GitHub Pages) |
| `demo.html` | Interactive demo / live resolver |
| `benchmark.html` | Benchmark results viewer |
| `design.md` | This file — UI source of truth |

When modifying `index.html` or `demo.html`, check this document first.
When the design system changes (new token, new component), update this file
first, then propagate to HTML files.

---

## 9. Current Headline Stats (as of 2026-05-14)

These numbers appear in stat cards, meta descriptions, and the demo video
script. Keep them in sync when tests are added or changed.

| Metric | Value |
|---|---|
| Python tests | 541 passing, 3 skipped |
| Foundry (Solidity) tests | 55 passing |
| Parity tests (Python ↔ Solidity) | 14 |
| Adversarial simulation tests | 90 (59 + 31) |
| Sybil resistance tests | 83 |
| Total test count | 596 (541 Python + 55 Foundry) |
| Benchmark accuracy | 100% (50-case, seed=42; DISPUTE=valid abstention; swarm Brier 0.0724 vs 0.1029 best agent) |
| Contracts deployed | 4 (Base Sepolia) |
| External dependencies | 0 (Python core) |

---

## 10. Do Not

- Do not introduce new color values without adding them to `:root` as tokens first
- Do not use `font-family: sans-serif` inline — use the token variables
- Do not add JavaScript frameworks or CDN scripts to `index.html` (intentionally zero-dependency)
- Do not use `localStorage` (not supported in the Claude artifact sandbox)
- Do not change the decision color palette (YES=green, NO=red, DISPUTE=amber)
- Do not hardcode contract addresses as text — always wrap in an anchor to Basescan
