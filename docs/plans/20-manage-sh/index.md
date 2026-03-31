# Plan: Unified `manage.sh` Service & Snapshot Manager

| Field          | Value                                                    |
|----------------|----------------------------------------------------------|
| Date           | 2026-03-31                                               |
| Branch         | `functional-improvements`                                |
| Predecessors   | None                                                     |
| Goal           | Replace `scripts/launch.sh` with `scripts/manage.sh` — a single entry point for service lifecycle **and** data persistence (snapshots with pg_dump + media_store bundling) |

## Context

`launch.sh` runs `docker compose down -v` in `do_start()` on every start, destroying
all PostgreSQL data. This is fine for quick dev but hostile to:

- **Personal long-running use** — accumulated knowledge graphs wiped on restart
- **Demo/testing workflows** — no way to save a "known good" state and restore it
- **Ops iteration** — can't quickly switch between datasets

The new `manage.sh` keeps the full start/stop lifecycle and adds snapshot management:
save, list, load, delete — covering both the DB (pg_dump) and media files.

## Strategy

Six stages, each independently testable and committable:

1. **Skeleton + utilities** — argument parser, shared functions, config vars
2. **start / stop** — service lifecycle (persist-by-default, `--fresh` to wipe)
3. **snapshot save** — pg_dump + tar media_store into `backups/`
4. **snapshot list** — enumerate snapshots with metadata
5. **snapshot load + delete** — restore from backup, remove old snapshots
6. **Integration** — update `run_e2e.sh`, delete `launch.sh`, update `CLAUDE.md`

## Success Criteria

| Criterion | Target |
|-----------|--------|
| `manage.sh start` preserves data | Existing volume reused, no `down -v` |
| `manage.sh start --fresh` wipes cleanly | Equivalent to old `launch.sh` behavior |
| `manage.sh stop` keeps PG data | Volume survives, `stop --all` stops PG too |
| `snapshot save` creates archive | `backups/<name>-<date>.tar.gz` with db.sql.gz + media_store + metadata |
| `snapshot list` shows metadata | Name, date, size, media yes/no |
| `snapshot load` restores state | DB replaced via pg_dump restore, media_store replaced |
| `snapshot delete` removes archive | File removed, confirmation prompt (skippable with `--yes`) |
| `run_e2e.sh` uses manage.sh | No more inlined lifecycle logic |
| `launch.sh` deleted | All references updated |

## Files That May Be Changed

| File | Change |
|------|--------|
| `scripts/manage.sh` | **New** — unified management script |
| `scripts/launch.sh` | **Deleted** |
| `scripts/run_e2e.sh` | Updated to delegate lifecycle to `manage.sh` (local mode only; `--docker` mode unchanged) |
| `CLAUDE.md` | References updated (launch.sh -> manage.sh) |
| `.claude/skills/neocortex/SKILL.md` | References updated (launch.sh -> manage.sh) |
| `.claude/skills/neocortex/KNOWN_ISSUES.md` | References updated (launch.sh -> manage.sh) |
| `.gitignore` | Add `backups/` |

## Progress Tracker

| # | Stage | Status | Notes | Commit |
|---|-------|--------|-------|--------|
| 1 | [Skeleton + utilities](stages/01-skeleton.md) | DONE | Skeleton with dispatch, utilities ported from launch.sh, status cmd, help | feat(scripts): add manage.sh skeleton |
| 2 | [start / stop](stages/02-start-stop.md) | DONE | do_start with --fresh flag, do_stop with --all flag, persist-by-default semantics | feat(scripts): implement start/stop |
| 3 | [snapshot save](stages/03-snapshot-save.md) | DONE | snapshot sub-dispatcher + save with pg_dump + media bundling + metadata JSON, stubs for list/load/delete, backups/ in .gitignore | feat(scripts): add snapshot save |
| 4 | [snapshot list](stages/04-snapshot-list.md) | DONE | Formatted table with NAME/DATE/SIZE/MEDIA, handles empty dir, corrupted archives, missing metadata | feat(scripts): add snapshot list |
| 5 | [snapshot load + delete](stages/05-snapshot-load-delete.md) | DONE | resolve_snapshot helper, load with --force flag + auto-stop services, delete with --yes flag + confirmation prompt | feat(scripts): add snapshot load and delete commands |
| 6 | [Integration](stages/06-integration.md) | DONE | run_e2e.sh delegates to manage.sh, launch.sh deleted, CLAUDE.md + SKILL.md + KNOWN_ISSUES.md updated, no stale refs | refactor(scripts): replace launch.sh with manage.sh |

Statuses: `PENDING` -> `IN_PROGRESS` -> `DONE` | `BLOCKED` | `SKIPPED`

## Execution Protocol

To execute this plan, follow this loop for each stage:

1. **Read the progress tracker** above and find the first stage that is not DONE
2. **Read the stage file** -- follow the link in the tracker to the stage's .md file
3. **Read resources** -- if the stage references shared resources,
   find them in the `resources/` directory
4. **Clarify ambiguities** -- if anything is unclear or multiple approaches exist,
   ask the user before implementing. Do not guess.
5. **Implement** -- execute the steps described in the stage
6. **Validate** -- run the verification checks listed in the stage.
   If validation fails, fix the issue before proceeding. Do not skip verification.
7. **Update this index** -- mark the stage as DONE in the progress tracker,
   add brief notes about what was done and any deviations
8. **Commit** -- create an atomic commit with the message specified in the stage.
   Include all changed files (code, config, docs, and this plan's index.md).

Repeat until all stages are DONE or a stage is BLOCKED.

**If a stage cannot be completed**: mark it BLOCKED in the tracker with a note
explaining why, and stop. Do not proceed to subsequent stages.

**If assumptions are wrong**: stop, document the issue in the Issues section below,
revise affected stages, and get user confirmation before continuing.

## Issues

_(populated during execution)_

## Decisions

| Decision | Rationale |
|----------|-----------|
| pg_dump for backups (not Docker volume copy) | Portable, inspectable, smaller than raw volume tarballs |
| Bundle media_store in snapshots | User preference — complete state restoration |
| Persist by default | Long-running personal use is the primary workflow |
| Replace launch.sh (not coexist) | Single entry point reduces confusion |
