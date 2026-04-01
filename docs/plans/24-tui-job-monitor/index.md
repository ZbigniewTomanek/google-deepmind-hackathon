# Plan: TUI Job Monitor

**Date**: 2026-04-01
**Branch**: feat/tui-job-monitor
**Predecessors**: None
**Goal**: Add a live job monitoring panel to the NeoCortex TUI showing job counts by status, a scrollable job list, detail drill-down, and cancel/retry actions.

---

## Context

The NeoCortex extraction pipeline enqueues async jobs via Procrastinate (`extract_episode`, `route_episode`) into the `procrastinate_jobs` PostgreSQL table. There is currently **no way to observe job status** except by querying the database directly. The TUI has three modes (remember, recall, discover) but no job visibility.

**Procrastinate job statuses**: `todo` (queued), `doing` (processing), `succeeded`, `failed`, `cancelled`.

**Key decisions from planning:**

| Question | Decision | Rationale |
|----------|----------|-----------|
| Data access | REST endpoints on ingestion API | Conventional for monitoring; keeps DB access server-side |
| Scope | Current agent default, toggle for all | Useful for both single-agent and admin debugging |
| Refresh | Auto-polling (~3-5s) | Monitoring should feel live |
| Actions | Cancel + retry | Full interactive control from TUI |
| Job tree | Flat list | No parent-child tracking in DB; simplest approach |

---

## Strategy

**Phase A (Backend):** Add REST endpoints for job listing, detail, cancel, retry to the admin router on the ingestion API. Query `procrastinate_jobs` directly via the shared asyncpg pool.

**Phase B (TUI Client):** Add an HTTP client in the TUI for calling the admin REST API (separate from the MCP client). The TUI's `--url` flag already points at the server; ingestion API runs on port 8001 — add `--ingestion-url` flag.

**Phase C (TUI UI):** Add a "Jobs" mode with status summary bar, job list table, auto-polling, detail drill-down, and cancel/retry actions.

---

## Success Criteria

| Metric | Baseline | Target | Rationale |
|--------|----------|--------|-----------|
| Job visibility | 0 (no UI) | All 5 statuses visible with counts (todo, doing, succeeded, failed, cancelled) | Core requirement |
| Refresh latency | N/A | <5s poll interval | Jobs mode should feel live |
| Job actions | None | Cancel + retry from TUI | Interactive control |
| Detail view | None | Task name, args, timestamps, attempts, error | Debugging support |

---

## Files That May Be Changed

### Backend (REST API)
- `src/neocortex/admin/routes.py` — Add job monitoring endpoints
- `src/neocortex/ingestion/app.py` — Expose pool on app.state for job queries

### TUI
- `src/neocortex/tui/__main__.py` — Add `--ingestion-url` CLI flag
- `src/neocortex/tui/app.py` — Add Jobs mode (widgets, CSS, key bindings, async workers, renderers)
- `src/neocortex/tui/client.py` — Add `JobsClient` HTTP class for admin REST API

### Tests
- `tests/test_admin_jobs.py` — Unit tests for job REST endpoints

---

## Progress Tracker

| # | Stage | Status | Notes | Commit |
|---|-------|--------|-------|--------|
| 1 | [REST API job endpoints](stages/01-rest-api-job-endpoints.md) | DONE | Pool on app.state, 6 endpoints (list/summary/detail/cancel/retry + mock guard), 18 tests | `feat(admin): add REST endpoints for job monitoring` |
| 2 | [TUI jobs HTTP client](stages/02-tui-jobs-http-client.md) | PENDING | | |
| 3 | [TUI jobs mode layout](stages/03-tui-jobs-mode-layout.md) | PENDING | | |
| 4 | [Auto-polling refresh](stages/04-auto-polling-refresh.md) | PENDING | | |
| 5 | [Job actions and detail view](stages/05-job-actions-detail-view.md) | PENDING | | |

Statuses: `PENDING` -> `IN_PROGRESS` -> `DONE` | `BLOCKED` | `SKIPPED`

---

## Execution Protocol

To execute this plan, follow this loop for each stage:

1. **Read the progress tracker** above and find the first stage that is not DONE
2. **Read the stage file** — follow the link in the tracker to the stage's .md file
3. **Read resources** — if the stage references shared resources,
   find them in the `resources/` directory
4. **Clarify ambiguities** — if anything is unclear or multiple approaches exist,
   ask the user before implementing. Do not guess.
5. **Implement** — execute the steps described in the stage
6. **Validate** — run the verification checks listed in the stage.
   If validation fails, fix the issue before proceeding. Do not skip verification.
7. **Update this index** — mark the stage as DONE in the progress tracker,
   add brief notes about what was done and any deviations
8. **Commit** — create an atomic commit with the message specified in the stage.
   Include all changed files (code, config, docs, and this plan's index.md).

Repeat until all stages are DONE or a stage is BLOCKED.

**If a stage cannot be completed**: mark it BLOCKED in the tracker with a note
explaining why, and stop. Do not proceed to subsequent stages.

**If assumptions are wrong**: stop, document the issue in the Issues section below,
revise affected stages, and get user confirmation before continuing.

---

## Issues

[Document any problems discovered during execution]

---

## Decisions

- REST endpoints go on admin router (require admin for "all agents" view, but allow non-admin for own-agent jobs)
- TUI uses `httpx` for REST calls (already a transitive dependency via fastmcp)
- Procrastinate cancel uses `UPDATE SET status='cancelled'` (native enum value) — there's no graceful in-flight cancel, but `todo` jobs can be prevented from running
- Retry = re-defer the same task with same args as a new job
