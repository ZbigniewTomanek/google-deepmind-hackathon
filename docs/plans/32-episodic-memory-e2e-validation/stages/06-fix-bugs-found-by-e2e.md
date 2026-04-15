# Stage 6: Fix Bugs Found by E2E Run

**Goal**: Fix the production and infrastructure bugs discovered when running the E2E test script against a live server, and get the full test suite to pass.
**Dependencies**: Stages 1-5 must be DONE (test script must exist)

---

## Context

Running the E2E test (`./scripts/run_e2e.sh scripts/e2e_episodic_memory_test.py`) against a live server revealed **five bugs** — three infrastructure, one test-data design flaw, and one production logic bug. Three have been fixed; two remain.

### Bugs Found

| # | Bug | Severity | Status | Fix |
|---|-----|----------|--------|-----|
| B1 | **Startup race**: MCP + ingestion servers start concurrently, both call `create_services()` which provisions shared schemas, causing `asyncpg.exceptions.InternalServerError: tuple concurrently updated` | Blocker | **FIXED** | `manage.sh`: wait for MCP health before starting ingestion |
| B2 | **Token file override**: `.env` has `NEOCORTEX_DEV_TOKENS_FILE=dev_tokens.json`; `manage.sh` sources `.env` with `set -a` which overwrites the `dev_tokens_test.json` exported by `run_e2e.sh` → 401 on ingestion calls | Blocker | **FIXED** | `manage.sh`: save/restore `NEOCORTEX_DEV_TOKENS_FILE` around `.env` sourcing |
| B3 | **1-based session sequences**: Test expected 0-based `session_sequence`, but both DB adapter and mock use `COALESCE(MAX(session_sequence), 0) + 1` (1-based) | Test bug | **FIXED** | `e2e_episodic_memory_test.py`: `enumerate(rows, start=1)` |
| B4 | **Neighbor expansion dead in production**: Two compounding issues made MemMachine neighbor expansion non-functional end-to-end | Production bug | **FIXED** | See details below |
| B5 | **Extraction `ModelAPIError: Connection error`**: `extract_episode` jobs fail with connection errors to OpenAI API (DNS: nodename nor servname provided) | Blocker for Stage 4+ | **FIXED** | Missing `OPENAI_API_KEY` in `.env` — extraction uses `openai-responses:gpt-5.4-mini`, not Gemini |

### B4 Detail: Neighbor Expansion Bug (two parts)

**Part A — `seen_episode_ids` too broad**: In `_recall_in_schema()`, `seen_episode_ids` was populated from ALL SQL-matched episodes. With the episode SQL `LIMIT` set equal to the user's `limit`, all candidates were "seen" before expansion ran, so no new neighbors could ever be discovered. Fix: over-fetch episodes (`episode_sql_limit = max(limit * 3, limit + 10)`), sort by vector_sim, and only mark the top `limit` as "seen" (nucleus candidates). Over-fetched episodes can then be discovered as session neighbors.

**Part B — Double truncation**: After `repo.recall()` returned results with neighbors preserved, the recall tool (`tools/recall.py` line 254) applied a second `all_results[:limit]` truncation. Since neighbors have 0.6x score, they always ranked below nucleus items and were cut. Fix: both `adapter.py:recall()` and `tools/recall.py` now truncate by counting only non-neighbor items toward `limit`; neighbors of surviving nuclei are preserved.

### Test Data Redesign

The original Session A data (4 turns, all about PostgreSQL) was too semantically homogeneous — all episodes matched any PG-related query via vector similarity, leaving nothing for neighbor expansion to surface. Session A was restructured to 6 turns spanning 3 topics: party planning (turns 1-2), PostgreSQL upgrade (turns 3-5), and hiring (turn 6). A PG-specific query now hits turns 3-5 as nucleus results, and expansion pulls in turns 2 and 6 as session context neighbors.

---

## Current State

All stages pass:
- **Stage 1**: PASSED (6 + 3 episodes ingested and verified in DB)
- **Stage 2**: PASSED (8 items returned: 5 nucleus + 3 neighbors, with correct session clustering)
- **Stage 3**: PASSED (STM boost confirmed — fresh episode outranks backdated content)
- **Stage 4**: PASSED (37 extraction jobs complete in ~450s; 47 nodes, 12 FOLLOWS edges)
- **Stage 5**: PASSED (combined recall returns 3 episodes + 47 nodes; formatted_context valid JSON)

## Steps to Complete

### 1. Investigate extraction connection error (B5)

The `extract_episode` task in `src/neocortex/jobs/tasks.py:69` calls `run_extraction()` which uses PydanticAI agents backed by Gemini. The `route_episode` task (domain classification) also uses Gemini and succeeds, so the API key is valid. Possible causes:
- Different model name or endpoint for extraction vs. routing
- Rate limiting after routing consumes the quota
- Network timeout on longer extraction calls

Check:
1. `GOOGLE_API_KEY` env var is set for the MCP server process (extraction worker runs inside MCP)
2. Compare model names used by routing (`domain_classifier_model`) vs extraction agents
3. Check `log/mcp_stdout.log` for the full error traceback
4. Try running extraction manually: `uv run python -c "from neocortex.extraction.pipeline import run_extraction; ..."`

### 2. Remove debug logging from adapter

- File: `src/neocortex/db/adapter.py`
- Remove the temporary `_nbr_logger.debug(...)` calls added during investigation (3 log statements near the neighbor expansion block). Keep the production code changes (over-fetch, nucleus-only `seen_episode_ids`).

### 3. Run full E2E suite

Once extraction works:
```bash
./scripts/run_e2e.sh scripts/e2e_episodic_memory_test.py
```

All 5 stages should pass. Verify that:
- Stage 4: FOLLOWS edges exist, extracted nodes appear in `discover_graphs`
- Stage 5: Combined recall returns both episodes and nodes; `formatted_context` is valid JSON

### 4. Run unit tests

```bash
uv run pytest tests/ -q --ignore=tests/test_graph_data.py --ignore=tests/test_scoped_connections.py --ignore=tests/test_schema_manager.py --ignore=tests/test_server_lifespan.py
```

All should pass (875+ passed in the last run). The ignored tests require a running PG instance.

---

## Files Changed (so far)

| File | Change | Status |
|------|--------|--------|
| `scripts/manage.sh` | Stagger startup (MCP health before ingestion), preserve `NEOCORTEX_DEV_TOKENS_FILE` across `.env` source | Done |
| `scripts/e2e_episodic_memory_test.py` | Fix 1-based sequences, restructure Session A data, add diagnostic output | Done |
| `src/neocortex/db/adapter.py` | Episode over-fetch, nucleus-only `seen_episode_ids`, neighbor-preserving truncation in `recall()` | Done |
| `src/neocortex/tools/recall.py` | Neighbor-preserving truncation in recall tool | Done |
| `scripts/e2e_episodic_memory_test.py` | Increased job timeout 120→600s, added failed-job tracking, raised combined-recall limit to 50, added score diagnostics | Done |

---

## Verification

- [x] Extraction connection error resolved (B5) — added `OPENAI_API_KEY` to `.env`
- [x] Debug logging removed from `adapter.py` — already clean (no `_nbr_logger` references)
- [x] Full E2E test passes: `./scripts/run_e2e.sh scripts/e2e_episodic_memory_test.py` — all 5 stages pass
- [x] Unit tests pass: 874 passed, 6 skipped, 15 errors (PG-dependent tests without running PG)
- [ ] No regressions in other E2E scripts (optional: not run — extraction takes ~8 min)

---

## Commit

`fix: repair neighbor expansion, startup race, and token override bugs found by E2E`

Include all 4 changed files. The commit message should reference Plan 32 Stage 6.
