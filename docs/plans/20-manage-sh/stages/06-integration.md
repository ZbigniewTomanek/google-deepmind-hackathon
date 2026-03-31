# Stage 6: Integration — Update References, Delete `launch.sh`

## Goal

Wire everything together: update `run_e2e.sh` to use `manage.sh`, remove `launch.sh`,
update documentation.

## Dependencies

- Stages 1–5 (all manage.sh functionality complete)

## Steps

1. **Update `scripts/run_e2e.sh`**:
   - Replace calls to `launch.sh` functions with `manage.sh` subcommands
   - The E2E script currently inlines similar logic (start PG, apply migrations,
     start servers). Refactor to call:
     - `manage.sh start --fresh` for clean test runs
     - `manage.sh stop --all` for teardown
   - Keep the trap/EXIT cleanup pattern but delegate to `manage.sh stop --all`
   - Preserve `KEEP_RUNNING` env var behavior (skip teardown)

2. **Delete `scripts/launch.sh`**:
   ```bash
   git rm scripts/launch.sh
   ```

3. **Update `CLAUDE.md`**:
   - In "Build & Test" section: replace `./scripts/launch.sh` references with `./scripts/manage.sh start` and `./scripts/manage.sh stop`
   - In "Scripts" section: replace launch.sh description with manage.sh description
   - Add snapshot commands to the scripts documentation

4. **Update `.env` or any other files** that reference `launch.sh` (search for it):
   ```bash
   grep -r "launch.sh" --include='*.md' --include='*.sh' --include='*.py' .
   ```

5. **Add `backups/` to `.gitignore`** if not already present (snapshots should not be committed).

## Verification

```bash
# launch.sh is gone
test ! -f scripts/launch.sh

# manage.sh is executable and works
./scripts/manage.sh help
./scripts/manage.sh start --fresh
curl -sf http://127.0.0.1:8000/health
./scripts/manage.sh stop --all

# No stale references
grep -r "launch.sh" --include='*.md' --include='*.sh' --include='*.py' . && echo "STALE REFS" || echo "OK"

# E2E still works (if time permits)
# ./scripts/run_e2e.sh scripts/some_test.sh

# backups/ is gitignored
echo "test" > backups/.test
git status backups/ | grep -q ".test" && echo "NOT IGNORED" || echo "OK: ignored"
rm -f backups/.test
```

## Commit

```
refactor(scripts): replace launch.sh with manage.sh, update references
```
