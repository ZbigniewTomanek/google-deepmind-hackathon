#!/usr/bin/env bash
# Deploy a plan directory scaffold for the task-planning skill.
#
# Creates a directory with:
#   index.md              — Central overview, progress tracker, success criteria
#   stages/NN-.md         — One file per stage (empty templates)
#   resources/            — Shared resources (queries, commands, configs, etc.)
#
# Usage:
#   deploy_plan.sh --name <plan-name> [--stages N] [--dir PATH]
#
# Options:
#   --name NAME     Plan directory name (required). e.g. "36g-token-blocking"
#   --stages N      Number of stage files to create (default: 3)
#   --dir PATH      Parent directory (default: docs/plans)
#   --dry-run       Print what would be created without creating anything
#   -h, --help      Show this help
#
# Examples:
#   deploy_plan.sh --name "36g-token-blocking" --stages 5
#   deploy_plan.sh --name "auth-middleware-rewrite" --stages 8 --dir plans

set -euo pipefail

# ── Defaults ─────────────────────────────────────────────────────────
NAME=""
STAGES=3
DIR="docs/plans"
DRY_RUN=false
TODAY=$(date '+%Y-%m-%d')

# ── Argument parsing ─────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --name)     NAME="$2"; shift 2 ;;
        --stages)   STAGES="$2"; shift 2 ;;
        --dir)      DIR="$2"; shift 2 ;;
        --dry-run)  DRY_RUN=true; shift ;;
        -h|--help)
            sed -n '2,/^$/{ s/^# //; s/^#$//; p }' "$0"
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            echo "Use --help for usage information" >&2
            exit 1
            ;;
    esac
done

if [[ -z "$NAME" ]]; then
    echo "ERROR: --name is required" >&2
    echo "Usage: deploy_plan.sh --name <plan-name> [--stages N] [--dir PATH]" >&2
    exit 1
fi

PLAN_DIR="$DIR/$NAME"

if [[ -d "$PLAN_DIR" ]] && ! $DRY_RUN; then
    echo "ERROR: Directory already exists: $PLAN_DIR" >&2
    echo "Remove it first or choose a different name." >&2
    exit 1
fi

# ── Helpers ──────────────────────────────────────────────────────────
create_file() {
    local path="$1"
    local content="$2"
    if $DRY_RUN; then
        echo "  [dry-run] $path"
        return
    fi
    mkdir -p "$(dirname "$path")"
    cat > "$path" <<< "$content"
}

# ── Build progress tracker rows ──────────────────────────────────────
tracker_rows=""
for (( i=1; i<=STAGES; i++ )); do
    num=$(printf "%02d" "$i")
    tracker_rows+="| $i | [Stage $i](stages/${num}-.md) | PENDING | | |
"
done

# ── index.md ─────────────────────────────────────────────────────────
read -r -d '' INDEX_CONTENT <<'TEMPLATE' || true
# Plan: [PLAN_TITLE]

**Date**: DATE_PLACEHOLDER
**Branch**: [branch-name]
**Predecessors**: [Links to predecessor plans, or "None"]
**Goal**: [One-sentence goal]

---

## Context

[Problem statement, background data, why this matters. Include tables, measurements,
and references to prior work. This section should give a cold reader enough context
to understand every stage.]

---

## Strategy

[High-level approach. If stages group into phases, describe them here.]

---

## Success Criteria

| Metric | Baseline | Target | Rationale |
|--------|----------|--------|-----------|
| [metric] | [current value] | [target value] | [why this target] |

---

## Files That May Be Changed

### [Category]
- `path/to/file` -- [What changes and why]

---

## Progress Tracker

| # | Stage | Status | Notes | Commit |
|---|-------|--------|-------|--------|
TRACKER_ROWS
Statuses: `PENDING` -> `IN_PROGRESS` -> `DONE` | `BLOCKED` | `SKIPPED`

---

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

---

## Issues

[Document any problems discovered during execution]

---

## Decisions

[Record architectural or approach decisions made during planning or execution]
TEMPLATE

INDEX_CONTENT="${INDEX_CONTENT//DATE_PLACEHOLDER/$TODAY}"
INDEX_CONTENT="${INDEX_CONTENT//TRACKER_ROWS/$tracker_rows}"

# ── Stage files ──────────────────────────────────────────────────────
generate_stage() {
    local num="$1"
    cat <<'STAGE'
# Stage NUM_PLACEHOLDER: [Name]

**Goal**: [What this stage accomplishes -- one sentence]
**Dependencies**: [What must be DONE first, or "None"]

---

## Steps

1. [Specific action -- include file paths, line references, exact values]
   - File: `path/to/file`
   - Details: [What to change]

2. [Specific action]
   - File: `path/to/file`
   - Details: [What to change]

---

## Verification

- [ ] [Concrete test command or check with expected outcome]
- [ ] [Another verification step]

---

## Commit

`type(scope): description`
STAGE
}

# ── resources/ ───────────────────────────────────────────────────────
read -r -d '' RESOURCES_README <<'RESOURCES' || true
# Shared Resources

This directory holds shared reference material used across stages.
Add files as needed -- common examples:

- **queries.md** -- Investigation queries, diagnostic SQL, API calls
- **commands.md** -- Build, test, deploy, and pipeline execution commands
- **configs.md** -- Reference configurations, environment variables, feature flags
- **data.md** -- Sample data, test fixtures, seed values
- **api-reference.md** -- Endpoint specs, request/response examples

Any file format works. Stages reference resources by relative path
(e.g., `see [queries](../resources/queries.md#q3)`).
RESOURCES

# ── Create everything ───────────────────────────────────────────────
echo "Deploying plan scaffold: $PLAN_DIR"
echo "  Stages: $STAGES"
echo ""

create_file "$PLAN_DIR/index.md" "$INDEX_CONTENT"

for (( i=1; i<=STAGES; i++ )); do
    num=$(printf "%02d" "$i")
    stage_content="$(generate_stage "$i")"
    stage_content="${stage_content//NUM_PLACEHOLDER/$i}"
    create_file "$PLAN_DIR/stages/${num}-.md" "$stage_content"
done

create_file "$PLAN_DIR/resources/README.md" "$RESOURCES_README"

echo ""
if $DRY_RUN; then
    echo "[dry-run] No files created."
else
    echo "Done. Plan scaffold created at: $PLAN_DIR/"
    echo ""
    echo "Next steps:"
    echo "  1. Fill in index.md (context, strategy, success criteria)"
    echo "  2. Rename and fill in stage files"
    echo "  3. Add resource files as needed (queries, commands, configs, etc.)"
    echo "  4. Review, then run via plan_runner.sh --plan $PLAN_DIR/index.md"
fi
