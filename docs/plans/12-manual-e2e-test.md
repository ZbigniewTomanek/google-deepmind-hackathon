# Plan 12: Comprehensive Manual E2E Test of NeoCortex Knowledge Engine

> **Report:** [01-full-e2e-knowledge-engine-validation](../reports/01-full-e2e-knowledge-engine-validation.md)

## Overview

Full end-to-end manual test exercising the complete NeoCortex pipeline: multi-format
ingestion (text, documents, audio, video), semantic domain routing to shared graphs,
episodic memory storage, ontology evolution, and graph-based recall with cognitive scoring.

We ingest real content from three sources, verify the internal knowledge representation
via MCP tools and TUI, then mutate the graph to observe ontology evolution.

## Pre-conditions

- PostgreSQL running on localhost:5432
- MCP server running on localhost:8000 (connected as Alice)
- Ingestion API running on localhost:8001 (dev_token auth)
- Alice token: `alice-token`, Admin token: `admin-token-neocortex`

## Baseline State

Alice's personal graph (`ncx_alice__personal`): 70 nodes, 91 edges, 27 episodes.
No shared graphs exist yet.

---

## Stage 1: Ingest E2E Fixtures (Audio + Video)

**Goal**: Test media ingestion pipeline (ffmpeg compression + Gemini description).

### Steps

1. Ingest `tests/e2e/fixtures/demo_clip.mp3` via `POST /ingest/audio`
2. Ingest `tests/e2e/fixtures/demo_clip.mp4` via `POST /ingest/video`
3. Verify both return `MediaIngestionResult` with `media_ref` (compressed path, duration)
4. Use MCP `recall` to search for content from the audio/video descriptions
5. Use MCP `discover` to check episode count increased by 2

### Verification

- [ ] Audio ingestion returns status=stored, media_ref present
- [ ] Video ingestion returns status=stored, media_ref present
- [ ] Recall finds content related to the media descriptions
- [ ] Episode count increased from 27 to 29+

---

## Stage 2: Ingest Entity Resolution Pipeline Docs

**Goal**: Test document ingestion and automatic domain routing to shared graphs.

### Content

Key files from `/Users/zbigniewtomanek/PycharmProjects/datawalk-entity-resolution/docs/mvp-plan/`:
- `README.md` — Architecture overview (21 KB)
- `01-schema/input-schema.md` — Data contract (16 KB)
- `03-blocking/blocking_strategies.md` — Blocking rules (23 KB)
- `00-er-functions/string-similarity.md` — String matching algorithms (15 KB)
- `02-features/comprehensive-feature-plan.md` — Feature engineering (37 KB)

### Steps

1. Ingest each file via `POST /ingest/document` with alice-token
2. Verify each returns status=stored
3. Check domain routing: these technical docs should auto-create shared domain graphs
   (e.g., `ncx_shared__technical_knowledge` or similar)
4. Use MCP `discover` to verify new shared graphs appear
5. Use MCP `recall` with queries like "entity resolution blocking strategies" and
   "Fellegi-Sunter probabilistic scoring" to verify content is searchable

### Verification

- [ ] All 5 documents ingested successfully
- [ ] Domain routing created shared graph(s) for technical content
- [ ] Alice has read+write permissions on auto-created domain graphs
- [ ] Recall returns relevant results for ER-specific queries
- [ ] New node types appear in ontology (e.g., Pipeline, Strategy, Function)

---

## Stage 3: Ingest Daily Notes (Personal Context)

**Goal**: Test text ingestion of personal/mixed content and domain routing for
non-technical content.

### Content

4 daily notes (2026-03-24 through 2026-03-27) from Obsidian vault containing:
- Work notes: ER pipeline scalability issues, WNP implementation, hackathon prep
- Health tracking: sleep, supplements, body battery
- Personal events: sauna, moving help, car sale, cat grooming
- Technical insights: blocking scalability, batch processing

### Steps

1. Ingest each daily note via `POST /ingest/text` with alice-token
   (strip Obsidian meta-bind widgets, keep substantive content)
2. Verify each returns status=stored
3. Check domain routing: expect routing to multiple domains
   (work_context, user_profile, technical_knowledge)
4. Use MCP `recall` with personal queries: "what happened with the car?",
   "how did the WNP implementation go?"

### Verification

- [ ] All 4 daily notes ingested successfully
- [ ] Domain routing classifies across multiple domains
- [ ] Personal content searchable via recall
- [ ] Work content searchable alongside ER pipeline docs

---

## Stage 4: Verify Knowledge Graph via MCP Tools

**Goal**: Use MCP tools (connected as Alice) to inspect the full graph state.

### Steps

1. `discover` — capture full ontology: node types, edge types, stats, graphs list
2. `recall "entity resolution pipeline architecture"` — verify ER docs integrated
3. `recall "blocking strategies scalability"` — verify cross-source linking
   (daily notes mentioning blocking + ER docs about blocking should co-activate)
4. `recall "hackathon preparation"` — verify personal context searchable
5. `recall "audio video demo clip"` — verify media content searchable

### Verification

- [ ] Discover shows multiple graphs (personal + shared domain graphs)
- [ ] Node count significantly increased from baseline 70
- [ ] Edge count significantly increased from baseline 91
- [ ] Cross-source recall works (daily notes + ER docs on same topic)
- [ ] Graph context shows meaningful node neighborhoods in recall results

---

## Stage 5: Mutate Graph via Remember + Observe Ontology Evolution

**Goal**: Store new memories via MCP `remember` and observe how the ontology
and graph structure evolve.

### Steps

1. `remember` a new technical insight about the ER pipeline:
   "The Weighted Node Pruning implementation reduced candidate pairs by 60% on the 5M
   dataset, making the 200M target feasible. The key insight was using ECBS edge weights
   with tier-based boosts for high-precision blocking rules."
   (importance: 0.9, context: "Entity Resolution pipeline optimization")

2. `remember` a cross-domain memory connecting hackathon and ER work:
   "The NeoCortex agent memory system being built for the Google DeepMind hackathon
   could be integrated with the Entity Resolution pipeline to provide persistent
   context about blocking rule performance across runs."
   (importance: 0.7, context: "Cross-project insight")

3. `remember` a personal preference:
   "I prefer using sauna sessions on Wednesday evenings as recovery after heavy
   physical work. The PNF stretching routine before bed helps with sleep quality."
   (importance: 0.5, context: "Health and wellness preferences")

4. After each remember, run `discover` to track ontology changes
5. Run `recall` queries to verify new memories integrate with existing graph

### Verification

- [ ] Each remember returns episode_id and extraction_job_id
- [ ] Discover shows new/updated node types after extraction completes
- [ ] New edges connect to existing nodes (e.g., WNP node connects to ER pipeline)
- [ ] Recall for "WNP results" returns both the new memory and earlier daily note content
- [ ] Spreading activation links related topics across sources

---

## Stage 6: TUI Visual Verification

**Goal**: Use the TUI to visually confirm the knowledge graph state.

### Steps

1. Launch TUI: `python -m neocortex.tui --url http://localhost:8000 --token alice-token`
2. **Discover mode**: Fetch ontology, verify node/edge types and graph list
3. **Recall mode**: Search for "entity resolution" — verify graph context visualization
   shows tree-style node neighborhoods
4. **Recall mode**: Search for "daily routine health" — verify personal content
5. **Remember mode**: Store a new memory about the test itself
6. **Discover mode**: Re-fetch to see updated stats

### Verification

- [ ] TUI connects successfully to MCP server
- [ ] Discover shows all graphs (personal + shared)
- [ ] Recall results display with graph context (tree visualization)
- [ ] Remember stores successfully and shows episode_id
- [ ] Stats update after new remember

---

## Execution Protocol

Execute stages 1-5 programmatically (curl + MCP tools), fixing issues on the go.
Stage 6 requires interactive TUI session — provide launch command and manual steps.

## Progress Tracker

| Stage | Status | Notes |
|-------|--------|-------|
| 1. Media ingestion | DONE | Audio+video ingested OK. **BUG FOUND**: seed domains had schema_names referencing non-existent schemas + no permissions. Fixed by provisioning via admin API. Domain routing now works — all 4 shared graphs visible. |
| 2. ER docs ingestion | DONE | 5 docs ingested, 420 nodes/301 edges total. Domain routing placed content in technical_knowledge + work_context + domain_knowledge shared graphs. Rich ER ontology created (Algorithm, PipelineStage, SchemaTable, Feature, MatchingEngine types). **ISSUE**: cross-domain ontology contamination in shared schemas (medical nodes retyped as ER types). |
| 3. Daily notes ingestion | DONE | 4 notes ingested, domain routing classified to user_profile + work_context + technical_knowledge. Cross-source linking works (daily notes ↔ ER docs). WNP concept found in 4 graphs simultaneously. |
| 4. MCP verification | DONE | 666 nodes, 483 edges, 40 episodes, 138 node types, 170 edge types across 5 graphs. Cross-source recall works (daily notes ↔ ER docs ↔ media). **SYSTEMIC ISSUE**: ontology contamination in shared graphs — extraction reuses existing types from mixed domains (e.g., "Creatine" typed as ProbabilisticModel, "Gabapentin" as Batch). |
| 5. Graph mutation | DONE | 3 memories stored, extracted to 742 nodes/544 edges. Ontology evolved with 12+ new types (MemorySystem, WeightingScheme, TemporalContext, etc.) and 10+ new edge types (BOOSTS, PRESERVES_METRIC, TRACKS_PERFORMANCE, etc.). Cross-project linking NeoCortex↔ER Pipeline confirmed. WNP activation reinforced 0.47→0.66 via spreading activation. |
| 6. TUI verification | READY | Module imports OK. Launch interactively — see instructions below. |

Last stage completed: 5
Last updated by: Claude Opus 4.6, 2026-03-28

---

## Results Summary

### Graph Growth (Baseline → Final)

| Metric | Baseline | After Media | After ER Docs | After Daily Notes | After Remember | Growth |
|--------|----------|-------------|---------------|-------------------|----------------|--------|
| Nodes | 70 | 100 | 420 | 666 | 742 | 10.6x |
| Edges | 91 | 112 | 301 | 483 | 544 | 6.0x |
| Episodes | 27 | 30 | 36 | 40 | 43 | 1.6x |
| Node Types | ~30 | ~38 | ~106 | ~138 | ~150 | 5.0x |
| Edge Types | ~34 | ~43 | ~127 | ~170 | ~188 | 5.5x |
| Graphs | 1 | 1 | 5 | 5 | 5 | 5x |

### Ingestion Formats Tested

| Format | Endpoint | File | Result |
|--------|----------|------|--------|
| Audio | /ingest/audio | demo_clip.mp3 (120s) | Compressed to opus 1.1MB, Gemini described |
| Video | /ingest/video | demo_clip.mp4 (120s) | Compressed to h264 1.9MB, Gemini described with full transcript |
| Document | /ingest/document | 5 ER pipeline markdown files (112KB total) | All stored, extracted to rich ontology |
| Text | /ingest/text | 4 daily notes + 1 test + 3 memories | All stored, multi-domain routing |

### Domain Routing Results

All 4 seed domains activated: `user_profile`, `technical_knowledge`, `work_context`, `domain_knowledge`.
Content classified and routed additively (personal graph always gets copy, shared graphs get domain extractions).

### Cognitive Features Observed

- **Spreading activation**: WNP node activation increased 0.47→0.66 through multiple recalls
- **Hebbian learning**: Edge weights increased on frequently traversed paths (e.g., SSRIs edges: 1.0→1.95)
- **Cross-source linking**: Daily notes ↔ ER docs ↔ media all interconnected via shared concept nodes
- **Temporal contexts**: Supplement routines extracted with TimeOfDay and DayOfWeek nodes

### Issues Found

1. **BUG (Fixed)**: Seed domains in `ontology_domains` table referenced schema names that didn't exist in
   `graph_registry`, and no permissions were granted. Fixed by provisioning schemas via admin API and
   granting alice read+write. **Root cause**: migration seeds domain records but doesn't create PG schemas.

2. **ISSUE**: Ontology contamination in shared graphs. When multiple content domains are extracted into the
   same shared schema, the extraction pipeline reuses existing node/edge types inappropriately:
   - "Creatine" typed as `ProbabilisticModel` (should be `Supplement`)
   - "Gabapentin" typed as `Batch` (should be `ChemicalSubstance`)
   - "Serotonin" typed as `DatabaseSystem` in technical_knowledge
   - "Tomasz Rozgalka" typed as `Action` (should be `Person`)

   **Root cause**: The extraction LLM sees existing types from a different domain and force-fits new
   entities into them. The ontology agent proposes types based on what's already in the schema.

3. **OBSERVATION**: `edge_skipped_missing_node` warnings during extraction — some edges reference nodes
   that weren't created (possibly filtered by the extraction pipeline).

### TUI Launch Instructions

To visually verify the graph state, run in a separate terminal:

```bash
cd /Users/zbigniewtomanek/work/google-deepmind-hackathon
uv run python -m neocortex.tui --url http://localhost:8000 --token alice-token
```

**Verification steps:**
1. Press `d` → Discover mode → click "Fetch Ontology" — verify 742+ nodes, 544+ edges, 5 graphs
2. Press `q` → Recall mode → search "entity resolution" — verify graph context tree visualization
3. Press `q` → Recall mode → search "supplements routine" — verify personal content
4. Press `r` → Remember mode → store a test memory → verify episode_id returned
5. Press `d` → Discover mode → re-fetch → verify stats incremented
