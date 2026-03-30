# Templates & Examples

## Directory Structure

```
plan-name/
├── index.md              # Central overview, progress tracker, success criteria
├── stages/
│   ├── 01-stage-name.md  # Individual stage details
│   ├── 02-stage-name.md
│   └── ...
└── resources/
    ├── queries.md        # Investigation queries, SQL templates
    └── commands.md       # Pipeline execution commands
```

---

## index.md Template

````markdown
# Plan: [Task Name]

**Date**: YYYY-MM-DD
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

**Phase A** (Stages 1-2): [Description]
**Phase B** (Stages 3-5): [Description]

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
| 1 | [Stage Name](stages/01-stage-name.md) | PENDING | | |
| 2 | [Stage Name](stages/02-stage-name.md) | PENDING | | |
| 3 | [Stage Name](stages/03-stage-name.md) | PENDING | | |

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

### Issue: [Title]
- **Expected**: [What should have happened]
- **Actual**: [What happened]
- **Impact**: [How this affects the plan]
- **Resolution**: [What was done or proposed]

---

## Decisions

[Record architectural or approach decisions made during planning or execution]

### Decision: [Title]
- **Options**: A) [...] B) [...] C) [...]
- **Chosen**: [Option]
- **Rationale**: [Why]
````

---

## Stage File Template

File: `stages/NN-stage-name.md`

````markdown
# Stage N: [Name]

**Goal**: [What this stage accomplishes -- one sentence]
**Dependencies**: [What must be DONE first, or "None"]

---

## Steps

1. [Specific action -- include file paths, line references, exact values]
   - File: `path/to/file`
   - Details: [What to change, with before/after if helpful]

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
````

---

## resources/ — Shared Reference Material

The `resources/` directory holds any shared material that stages reference.
It is not prescriptive -- add whatever files the plan needs. Common examples:

| File | Purpose | Example content |
|------|---------|-----------------|
| `queries.md` | Investigation queries | SQL, GraphQL, API calls, curl commands |
| `commands.md` | Build/test/deploy commands | Shell commands for each environment |
| `configs.md` | Reference configurations | Env vars, feature flags, YAML snippets |
| `data.md` | Sample data, fixtures | Test inputs, seed values, expected outputs |
| `api-reference.md` | Endpoint specs | Request/response examples, auth setup |
| `migration.md` | Schema/data migration | DDL, migration scripts, rollback steps |

Use placeholders (e.g., `{schema}`, `{env}`, `${API_URL}`) for portability
across environments. Stages reference resources by relative path
(e.g., `see [queries](../resources/queries.md#q3)`).

---

## Simple Plan Template (Single File)

For tasks with fewer than 5 steps that don't need a directory:

````markdown
# Plan: [Task Name]

## Overview
[What and why -- one paragraph]

## Steps
1. [Action verb] [specific change]
   - File: [path]
   - Details: [what to change]
2. [Action verb] [specific change]
   ...

## Verification
- [ ] [Test command or check]

## Commit
`type(scope): brief description`
````

---

## Example: Complex Plan Directory

**Task**: "Migrate mixed person features from coarse to precise Metaphone3"

Deployed with:
```bash
deploy_plan.sh --name "36f-mixed-person-precision-migration" --stages 3
```

### index.md (abbreviated)

```markdown
# Plan: Mixed Person Precision Migration & Block Size Tuning

**Date**: 2026-03-30
**Branch**: CTO-3138
**Predecessors**: Plan 36d, Plan 36b
**Goal**: Eliminate coarse-metaphone3 bottleneck in mixed person composed features

## Context
Plan 36d migrated org features but left mixed person features on 4-char coarse.
At 30M, mixed_person_name_city generates 212M pairs (6.60x super-linear scaling).

## Strategy
**Phase A** (Stage 1): YAML-only config migration + sandbox validation
**Phase B** (Stages 2-3): 30M benchmark + scaling analysis

## Success Criteria
| Metric | Baseline | Target |
|--------|----------|--------|
| Sandbox blocking recall | 79.64% | >= 78% |
| 30M total pairs | 661M | < 500M |

## Progress Tracker
| # | Stage | Status | Notes | Commit |
|---|-------|--------|-------|--------|
| 1 | [Config Migration](stages/01-config-migration.md) | DONE | 4 features switched, 2 caps tightened | abc1234 |
| 2 | [Sandbox Validation](stages/02-sandbox-validation.md) | DONE | Recall 79.1%, pairs/entity 2.3 | def5678 |
| 3 | [30M Benchmark](stages/03-30m-benchmark.md) | PENDING | | |

## Execution Protocol
[standard protocol]
```

### stages/01-config-migration.md

```markdown
# Stage 1: Config Migration

**Goal**: Switch 4 mixed person composed features from coarse to precise Metaphone3
**Dependencies**: None

## Steps
1. Update feature sources in `app/config/organization/features.yaml`
   - Lines 807, 827, 847, 867: change `features_mixed_person_name_metaphone3`
     to `features_mixed_person_name_metaphone3_precise`
2. Lower `mixed_person_name_only` cap from 500 to 200
   - File: `app/config/organization/blocking.yaml`, line 157
3. Lower `org_name_cleaned_exact` cap from 100 to 50
   - File: `app/config/organization/blocking.yaml`, line 129
4. Update test assertion
   - File: `tests/test_config_loader.py`, line 260: 100 -> 50

## Verification
- [ ] `poetry run pytest tests/test_config_loader.py` passes
- [ ] Config validates: all 4 composed features reference precise source

## Commit
`feat(blocking): migrate mixed person composed features to precise metaphone3`
```

### resources/queries.md (abbreviated)

```markdown
# Investigation Queries

## Connection
/opt/vertica/bin/vsql -h host -p 5433 -U user -w pass -c "..."

### Q-ALL: Combined metrics
SELECT entity_count, total_pairs, surviving_pairs, pairs_per_entity ...

### Q6: Blocking rule pair counts
SELECT blocking_rule, COUNT(*) AS pair_count FROM {schema}.er_blocking_rules ...
```
