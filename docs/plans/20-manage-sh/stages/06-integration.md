# Stage 6: Integration — Update References, Delete `launch.sh`

## Goal

Wire everything together: update `run_e2e.sh` to use `manage.sh`, remove `launch.sh`,
update documentation.

## Dependencies

- Stages 1–5 (all manage.sh functionality complete)

## Steps

1. **Update `scripts/run_e2e.sh`**:

   The E2E script currently inlines its own lifecycle logic (PG startup, migrations,
   server startup, port killing). It has two modes:

   - **Local mode** (default): starts PG in Docker, runs MCP + ingestion as local
     Python processes. This is the path to refactor.
   - **`--docker` mode**: runs everything via `docker compose up -d --build`.
     Leave this path unchanged — it doesn't use launch.sh and operates differently.

   Refactoring the local-mode path:
   - Replace the inline PG startup + migration + server startup block with:
     `"$SCRIPT_DIR/manage.sh" start --fresh`
   - Replace the `cleanup()` function's local-mode teardown with:
     `"$SCRIPT_DIR/manage.sh" stop --all`
   - Keep the `trap cleanup EXIT INT TERM` pattern — `cleanup()` still decides
     whether to skip (KEEP_RUNNING=1) or delegate to manage.sh
   - Keep `--docker` mode's own startup/cleanup paths untouched
   - Keep URL config overrides (`NEOCORTEX_BASE_URL`, `NEOCORTEX_INGESTION_BASE_URL`)
   - Keep `.env` sourcing before running the test script (line ~209)
   - Remove the duplicated `wait_for_healthy`, `kill_port`, and inline health-check
     functions that are now in manage.sh

2. **Delete `scripts/launch.sh`**:
   ```bash
   git rm scripts/launch.sh
   ```

3. **Update `CLAUDE.md`**:
   - In "Build & Test" section (lines 68-69): replace `./scripts/launch.sh` references
     with `./scripts/manage.sh start` and `./scripts/manage.sh stop`
   - In "Scripts" section (line 129): replace launch.sh description with manage.sh
     description, including snapshot commands

4. **Update `.claude/skills/neocortex/SKILL.md`** (lines 24, 34):
   - Replace `./scripts/launch.sh` with `./scripts/manage.sh start`
   - Replace `./scripts/launch.sh --stop` with `./scripts/manage.sh stop`

5. **Update `.claude/skills/neocortex/KNOWN_ISSUES.md`** (line 49):
   - Replace `./scripts/launch.sh` with `./scripts/manage.sh start`

6. **Search for any remaining references** and update them:
   ```bash
   grep -rn "launch.sh" --include='*.md' --include='*.sh' --include='*.py' --include='*.json' .
   ```
   Note: references in old plan docs (`docs/plans/12-*`, `docs/plans/14-*`,
   `docs/plans/17-*`, `docs/plans/19-*`) are historical records — do NOT update them.

7. **Add `backups/` to `.gitignore`** if not already present (snapshots should not be committed).

## Verification

```bash
# launch.sh is gone
test ! -f scripts/launch.sh

# manage.sh is executable and works
./scripts/manage.sh help
./scripts/manage.sh start --fresh
curl -sf http://127.0.0.1:8000/health
./scripts/manage.sh stop --all

# No stale references (ignore old plan docs which are historical)
grep -rn "launch.sh" --include='*.md' --include='*.sh' --include='*.py' . \
  | grep -v "docs/plans/1[2-9]" \
  | grep -v "docs/plans/20-manage-sh" \
  && echo "STALE REFS FOUND" || echo "OK: no stale refs"

# E2E works with refactored run_e2e.sh
./scripts/run_e2e.sh tests/e2e/test_basic_flow.py

# backups/ is gitignored
mkdir -p backups
echo "test" > backups/.test
git status backups/ | grep -q ".test" && echo "NOT IGNORED" || echo "OK: ignored"
rm -rf backups/.test
```

## Commit

```
refactor(scripts): replace launch.sh with manage.sh, update references
```
