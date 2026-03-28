# NeoCortex — Hackathon Showcase Presentation

## Goal

This presentation supplements a **live multi-agent technical demo** during the Google DeepMind x AI Tinkerers Hackathon showcase (Warsaw, March 2026). It is **not** a standalone pitch deck — it exists to frame the demo, convey architectural depth, and leave judges with a clear mental model of what NeoCortex does and why it matters.

**Target duration:** 3 minutes max (including demo time).

### Alignment with Hackathon Evaluation Criteria

From `docs/research/00-hackathon-context.md`, the judges reward:

1. **Running code over slides** (Joe Heitzeberg / AI Tinkerers ethos) — the presentation frames the demo, never replaces it.
2. **Architectural depth** (Koc: observability, Chrobok: security, Gmitrzuk: code quality) — slides must expose the multi-agent extraction pipeline, graph isolation, and MCP protocol usage.
3. **Graph-based memory as a differentiator** (Google DeepMind's Agentic GraphRAG direction) — position NeoCortex as a direct implementation of the knowledge-graph memory paradigm Google is betting on.
4. **No sales pitches** — raw engineering, honest trade-offs, show the wiring.

### Key Messages to Land

- AI agents lack persistent, structured memory. NeoCortex solves this via a knowledge graph exposed through MCP.
- Multi-agent extraction pipeline (ontology + entity + relation agents) builds the graph from unstructured input.
- Per-agent schema isolation + shared graph routing = collaboration without data leaks.
- This is not a wrapper around an LLM. It is infrastructure.

---

## Build Instructions

### Workflow: HTML → Preview → PPTX

1. **HTML Slides** (`html-slides/*.html`) — Source of truth. Preview in browser, iterate visually.
2. **Final PPTX** (`output/neocortex-presentation.pptx`) — Compiled PowerPoint from HTML slides.

### Directory Structure

```
docs/presentation/
├── index.md                    # This file (goals + style guide + build instructions)
├── compile-pptx.js             # Compilation script for generating PPTX
├── html2pptx.js                # HTML→PPTX converter (Playwright + pptxgenjs)
├── package.json                # Node dependencies
├── html-slides/                # HTML slides (source of truth)
│   └── slide-XX-name.html
├── assets/                     # Images, patterns, logos
└── output/                     # Final compiled PPTX (gitignored)
```

### Commands

```bash
cd docs/presentation
npm install                              # Install dependencies
open html-slides/slide-01-title.html     # Preview a slide in browser
node compile-pptx.js                     # Build PPTX from all HTML slides
```

---

## Style Guide: "Hive Mind" — Dark Terminal + Insect Memory

### Design Concept

The visual identity merges **insect colony intelligence** with **digital memory systems**. Ant colonies store distributed memory through pheromone trails (analogous to knowledge graph edges). Bee hives organize information in hexagonal structures (honeycomb = graph topology). The "hive mind" is the perfect metaphor for NeoCortex: a shared, structured memory that multiple agents access and build together.

**Aesthetic direction:** Dark, terminal-native, with warm amber and bioluminescent teal accents. Think HypGen Infinity meets a research lab's internal tooling. Not corporate, not marketing. The slide deck of someone who builds infrastructure.

### Color Palette

```css
:root {
  --ncx-void:       #04081A;   /* Background: deep Gemini void */
  --ncx-surface:    #0D1B3E;   /* Elevated surface: cards, panels */
  --ncx-grid:       #162D5A;   /* Subtle: grid lines, borders */
  --ncx-violet:     #9D6EF7;   /* Primary accent: violet */
  --ncx-violet-dim: #6B5B95;   /* Dimmed violet: secondary info */
  --ncx-teal:       #3ECFA0;   /* Secondary accent: bioluminescent, technical */
  --ncx-amber:      #C8A84E;   /* Tertiary: warm highlights */
  --ncx-text:       #E8E4DC;   /* Primary text: warm off-white */
  --ncx-text-muted: #6B5B95;   /* Muted text: dimmed violet */
}
```

### Typography

- **Headings / Code**: `"Share Tech Mono", "Courier New", monospace` — angular, hacker terminal
- **Body**: `"Outfit", "Arial", sans-serif` — clean, modern readability
- **Title**: 44pt, regular weight, `var(--ncx-text)`, letter-spacing: 0.35em (all-caps for main title)
- **Subtitle**: 16-18pt, light weight, `var(--ncx-violet)`
- **Body**: 14pt, regular, `var(--ncx-text)`
- **Code snippets**: 12pt, `var(--ncx-teal)`, monospace

### Slide Dimensions

- **16:9 ratio**: `width: 720pt; height: 405pt;`

### Layout Principles

- **Left-aligned** text (not centered, except title slide)
- **Generous whitespace** — never more than 3 ideas per slide
- **Monospace for structure** — use code-style formatting for architecture diagrams, tool names, protocol labels
- **Violet for emphasis**, teal for technical terms, amber for warm callouts
- **No logos** — the work speaks for itself
- **Static honeycomb pattern** as optional background texture (pre-rendered PNG in assets/)

### Visual Motifs

- **Hexagonal grid**: subtle background pattern suggesting graph topology + honeycomb structure
- **Thin horizontal rules**: amber or teal, used as section separators
- **Dotted borders**: on panels/cards, referencing the HypGen wireframe aesthetic
- **Node-edge diagrams**: when showing architecture, use circles (nodes) + lines (edges) in the accent palette

---

## Critical HTML Requirements for PPTX Compilation

The `html2pptx` converter has strict validation rules. **All slides must follow these**:

### 1. Text MUST Be Wrapped in Block Tags

All text must be inside `<p>`, `<h1>`-`<h6>`, `<ul>`, or `<ol>` tags.

```html
<!-- CORRECT -->
<div class="panel"><p>Knowledge Graph</p></div>

<!-- WRONG - Text will NOT appear in PowerPoint -->
<div class="panel">Knowledge Graph</div>
```

### 2. No CSS Gradients

```css
/* WRONG */
background: linear-gradient(135deg, #0A0D14 0%, #141820 100%);

/* CORRECT */
background: #0A0D14;
```

### 3. No Backgrounds/Borders/Shadows on Text Elements

Only `<div>` elements can have backgrounds, borders, or shadows. Never on `<p>`, `<h1>`-`<h6>`.

### 4. Minimum Bottom Margin

Content must end at least **0.5" (36pt)** from the bottom edge.

### 5. Web-Safe Font Fallbacks

Always include a web-safe fallback in font-family. Google Fonts load fine in HTML preview but PPTX uses the first font name — ensure it's installed or provide a safe fallback:
- `"Share Tech Mono", "Courier New", monospace`
- `"Outfit", "Arial", sans-serif`

---

## HTML Slide Template

```html
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Outfit:wght@300;400;600&display=swap" rel="stylesheet">
<style>
html { background: #04081A; }
body {
  width: 720pt;
  height: 405pt;
  margin: 0;
  padding: 0;
  background: #04081A;
  font-family: 'Outfit', Arial, sans-serif;
  position: relative;
  overflow: hidden;
}

.slide-content {
  margin: 40pt 50pt;
}

h1 {
  font-family: 'Share Tech Mono', 'Courier New', monospace;
  color: #E8E4DC;
  font-size: 32pt;
  font-weight: 400;
  margin: 0 0 16pt 0;
}

h2 {
  font-family: 'Share Tech Mono', 'Courier New', monospace;
  color: #9D6EF7;
  font-size: 20pt;
  font-weight: 400;
  margin: 0 0 12pt 0;
}

p {
  color: #E8E4DC;
  font-size: 14pt;
  line-height: 1.6;
  margin: 0 0 8pt 0;
}

.text-muted { color: #6B7280; }
.text-amber { color: #C8A84E; }
.text-teal  { color: #3ECFA0; }
</style>
</head>
<body>
  <div class="slide-content">
    <h1>Slide Title</h1>
    <p>Content goes here.</p>
  </div>
</body>
</html>
```

---

## Slide Plan (Draft)

| # | Slide | Purpose | Duration |
|---|-------|---------|----------|
| 01 | Title | NeoCortex identity, team, event context | 10s |
| 02 | The Problem | Agents are stateless. Memory is the missing piece. | 20s |
| 03 | What is NeoCortex | MCP server + knowledge graph = structured long-term memory | 20s |
| 04 | Architecture | Multi-schema isolation, graph router, MCP tools | 30s |
| 05 | Extraction Pipeline | 3-agent pipeline: ontology → entities → relations | 30s |
| 06 | Live Demo | **Switch to terminal** — remember, recall, discover flow | 60s |
| 07 | Security & Isolation | Per-agent schemas, RLS, permission model | 15s |
| 08 | Why Graphs | Vector search alone hallucinates. Graphs ground truth. | 15s |
| 09 | Closing | What we built, what's next | 10s |

Total: ~3 minutes (slide time ~2:30, demo ~60s integrated)
