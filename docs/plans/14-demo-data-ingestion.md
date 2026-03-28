# Plan 14: Demo Data Ingestion for Discovery Showcase

## Overview

Load real-world demo data into NeoCortex to showcase the discovery tools redesigned
in Plan 13. Data comes from three sources: Entity Resolution (ER) engine documentation,
an ER demo screen recording, and a Solution Innovation Team planning meeting recording.
All content targets a dedicated shared graph `ncx_shared__entity_resolution`.

### Motivation

Plan 13 redesigned the discovery API (`discover_domains`, `discover_graphs`,
`discover_ontology`, `discover_details`). To demo these tools effectively we need a
richly populated graph with diverse node/edge types extracted from real project artifacts.

### Data Sources

| # | Source | Original Size | Processed | Type |
|---|--------|--------------|-----------|------|
| 1 | `entity-resolution-overview.md` | 2 KB | as-is | document |
| 2 | `mvp-plan/README.md` | 64 KB | as-is | document |
| 3 | `principle-based-er-gap-analysis.md` | 39 KB | as-is | document |
| 4 | `Fellegi-Sunter Model Research.md` | 33 KB | as-is | document |
| 5 | `Senzing SDK Pipeline Consolidation Plan.md` | 27 KB | as-is | document |
| 6 | `data-sources.md` | 8 KB | as-is | document |
| 7 | `mvp-plan/00-er-functions/README.md` | 10 KB | as-is | document |
| 8 | `mvp-plan/02-features/README.md` | 13 KB | as-is | document |
| 9 | `mvp-plan/04-matching-engines/README.md` | 55 KB | as-is | document |
| 10 | `mvp-plan/datawalk-integration/README.md` | 42 KB | as-is | document |
| 11 | ER demo video (`~/Movies/2026-03-13 17-02-19.mp4`) | 179 MB / 14 min | Compressed to 14 MB (480p, CRF 32) | video |
| 12 | Meeting audio (`~/Downloads/...Recording.mp4`) | 353 MB / 31 min | Extracted MP3 28 MB, compressed to 13 MB opus | audio |

All docs from `~/work/entity-resolution-worktree-1/docs/`.

---

## Stage 1: Infrastructure Setup

**Status**: DONE

### Steps

1. Start services via `./scripts/launch.sh` (PG + MCP :8000 + ingestion :8001)
2. Fix ingestion server crash (duplicate schema race condition on startup) by manual restart with `NEOCORTEX_AUTH_MODE=dev_token`
3. Create shared graph `ncx_shared__entity_resolution` via admin API
4. Grant `dev-user` read+write permissions on the shared graph

### Verification

- [x] `curl localhost:8000/health` returns OK
- [x] `curl localhost:8001/health` returns OK
- [x] `graph_registry` contains `ncx_shared__entity_resolution`
- [x] `graph_permissions` grants `dev-user` r/w access

### Issues Found

- **Ingestion server startup race**: Both MCP and ingestion servers call `create_services`
  which provisions seed domain schemas. Second server hits `UniqueViolationError` on
  `pg_namespace_nspname_index` for `ncx_shared__technical_knowledge`. Known PG race on
  concurrent `CREATE SCHEMA IF NOT EXISTS`. Workaround: restart ingestion server after
  MCP is healthy (schemas already exist in registry, so `get_graph` returns early).

---

## Stage 2: Media Pre-processing

**Status**: DONE

### Steps

1. Compress ER demo video to under 100 MB ingestion limit:
   ```bash
   ffmpeg -y -i "~/Movies/2026-03-13 17-02-19.mp4" \
     -vf scale=-2:480 -c:v libx264 -crf 32 -preset fast \
     -c:a aac -b:a 64k -ac 1 /tmp/er_demo_compressed.mp4
   ```
   Result: 179 MB -> 14 MB

2. Extract audio from meeting recording:
   ```bash
   ffmpeg -y -i "~/Downloads/...Recording.mp4" \
     -vn -acodec libmp3lame -b:a 128k -ac 1 /tmp/meeting_planning.mp3
   ```
   Result: 353 MB -> 28 MB MP3 (further compressed to 13 MB opus by ingestion)

### Verification

- [x] `/tmp/er_demo_compressed.mp4` < 100 MB (14 MB)
- [x] `/tmp/meeting_planning.mp3` < 100 MB (28 MB)

---

## Stage 3: Episode Ingestion

**Status**: DONE

### Steps

1. Ingest 10 ER documentation files via `/ingest/document` with
   `--target ncx_shared__entity_resolution` and appropriate metadata
2. Ingest compressed video via `/ingest/video` (Gemini generates description)
3. Ingest meeting MP3 via `/ingest/audio` (Gemini generates transcript/description)

### Verification

- [x] 12 episodes in `ncx_shared__entity_resolution.episode`
- [x] All status: `"stored"`
- [x] Video media_ref: 14 min, 16 MB compressed
- [x] Audio media_ref: 31 min, 13 MB opus

---

## Stage 4: Extraction Pipeline

**Status**: IN_PROGRESS

### Steps

1. Wait for extraction jobs to process all 12 episodes into nodes/edges

### Bug Fix Applied

**`source_schema` sentinel mismatch in `jobs/tasks.py`**

The `extract_episode` task passes `source_schema=None` (its default when absent
from job args) to `run_extraction`. But in the pipeline, `None` explicitly means
"read from personal graph", while the sentinel `_UNSET` means "read from
target_schema". This caused all extraction jobs to look for episodes in the
agent's personal graph (`ncx_devuser__memory`) instead of the shared graph
(`ncx_shared__entity_resolution`), resulting in `episode_not_found` for all 12 jobs.

**Fix** (`src/neocortex/jobs/tasks.py`): Only pass `source_schema` when explicitly
provided, letting `run_extraction` use its `_UNSET` default:

```python
extra: dict = {}
if source_schema is not None:
    extra["source_schema"] = source_schema

await run_extraction(..., **extra, ...)
```

After fix, re-queued jobs extract successfully.

### Verification

- [x] Single test job (episode 1) extracts 14 nodes, 12 edges — no `episode_not_found`
- [x] All 12 jobs reach `succeeded` status
- [x] Graph: 178 nodes (50 types), 123 edges (44 types) — richly diverse

---

## Stage 5: Discovery Validation

**Status**: PENDING

### Steps

1. Use MCP `discover_graphs` to list available graphs including `ncx_shared__entity_resolution`
2. Use `discover_ontology` to inspect node/edge types in the graph
3. Use `discover_details` to drill into specific types and verify rich content
4. Use `recall` to search the graph and confirm hybrid scoring works across shared graph

### Verification

- [ ] `discover_graphs` shows `ncx_shared__entity_resolution` with node/edge counts
- [ ] `discover_ontology` returns diverse types (Concept, Tool, Person, Dataset, etc.)
- [ ] `discover_details` returns nodes with embeddings and content
- [ ] `recall` for "entity resolution" returns relevant results from the shared graph

---

## Progress Tracker

| Stage | Description | Status | Notes |
|-------|-------------|--------|-------|
| 1 | Infrastructure Setup | DONE | Services running, shared graph created, permissions granted |
| 2 | Media Pre-processing | DONE | Video 179->14MB, audio 353->28->13MB |
| 3 | Episode Ingestion | DONE | 12 episodes stored (10 docs, 1 video, 1 audio) |
| 4 | Extraction Pipeline | DONE | Bug fixed in tasks.py, 178 nodes / 123 edges extracted |
| 5 | Discovery Validation | IN_PROGRESS | Running discovery tool checks |

**Last stage completed**: Stage 4
**Last updated by**: Claude Opus 4.6 @ 2026-03-28
