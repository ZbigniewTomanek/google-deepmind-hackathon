---
name: task-planning
description: "Systematic task planning framework. Guides through analysis, clarification, and plan materialization as a directory with central index, per-stage files, and shared resources. Plans are designed for review by the user and autonomous execution by an AI agent via plan_runner.sh. Use for multi-step tasks, architectural changes, or complex problem-solving. Trigger when user asks to plan, break down, structure, or design implementation of a non-trivial task."
---

# Task Planning

Systematic workflow for planning non-trivial tasks. Produces a **plan directory**
with a central index, individual stage files, and shared resources. The user
reviews and refines the plan; execution is handled separately by an autonomous
agent via `plan_runner.sh`.

## Contents

- [Quick Start Checklist](#quick-start-checklist)
- [Phase 1: Analysis](#phase-1-analysis)
- [Phase 2: Clarification](#phase-2-clarification)
- [Phase 3: Plan Materialization](#phase-3-plan-materialization)
- [Headless Execution](headless.md)
- [Templates & Examples](templates.md)

## Quick Start Checklist

```
Planning Progress:
- [ ] Phase 1: Analyze context (read docs, explore code, identify root cause)
- [ ] Phase 2: Clarify ambiguity (ask questions if needed)
- [ ] Phase 3: Write plan directory (deploy scaffold, fill index + stages + resources)
```

---

## Phase 1: Analysis

**Goal**: Understand the problem space before proposing solutions.

1. **Read relevant docs** -- project README, CLAUDE.md, architecture docs, related plans
2. **Explore the codebase** -- entry points, execution flow, data structures, existing tests
3. **Identify root cause** -- don't treat symptoms; use git history, dependency analysis, impact analysis
4. **Synthesize findings** -- document problem statement, context, and 2-3 potential approaches with trade-offs

Present findings before moving to Phase 2:

```markdown
**Problem**: [What is actually broken or missing]
**Context**: [Relevant architecture, patterns, constraints]
**Approaches**:
  A. [Description] -- Pros: [...] Cons: [...]
  B. [Description] -- Pros: [...] Cons: [...]
**Recommendation**: [Which approach and why]
```

---

## Phase 2: Clarification

**Goal**: Resolve ambiguity before writing the plan.

### Ask questions when

- Multiple valid approaches exist and trade-offs need user input
- Scope is uncertain (minimal fix vs complete solution)
- Architecture choices affect future work
- Breaking changes are involved

### Don't ask about

- Standard patterns (follow existing code)
- Code formatting (use project conventions)
- How to use tools (read docs first)

### Question format

Use AskUserQuestion with options structured as:

```
Option 1: [Brief description]
- Pros: [benefits]
- Cons: [drawbacks]

Option 2: [Brief description]
- Pros: [benefits]
- Cons: [drawbacks]

Recommendation: Option [X] because [reasoning]
```

Skip Phase 2 entirely if the task is straightforward with clear requirements.

---

## Phase 3: Plan Materialization

**Goal**: Produce a plan directory that an autonomous agent can execute cold.

### Simple tasks (<5 steps)

Use a single markdown file (no directory needed):

```markdown
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
```

### Complex tasks (>=5 steps or multiple concerns)

**Deploy the directory scaffold** using the helper script:

```bash
~/.claude/skills/task-planning/scripts/deploy_plan.sh \
  --name "36g-token-blocking" \
  --stages 5 \
  --dir docs/plans
```

This creates:

```
docs/plans/36g-token-blocking/
├── index.md                  # Central overview, progress tracker, success criteria
├── stages/
│   ├── 01-.md                # One file per stage
│   ├── 02-.md
│   ├── 03-.md
│   ├── 04-.md
│   └── 05-.md
└── resources/
    ├── queries.md            # Investigation queries, SQL templates
    └── commands.md           # Pipeline/build/test commands
```

Then fill in the templates. See [templates.md](templates.md) for the full template
reference with field descriptions.

### Directory structure principles

| Component | Purpose | Rule |
|-----------|---------|------|
| `index.md` | Central overview + progress tracker | Everything an agent needs to orient itself |
| `stages/NN-name.md` | One stage per file | Self-contained: goal, steps, verification, commit |
| `resources/` | Shared queries, commands, data | Referenced from stages, not duplicated |

### Writing the index.md

The index is the **single entry point** for both human reviewers and the autonomous
agent. It must contain:

1. **Metadata** -- date, branch, predecessors, goal
2. **Context** -- problem statement, background data, why this matters
3. **Strategy** -- high-level approach, phases if stages group logically
4. **Success criteria** -- measurable targets with baselines
5. **Files that may be changed** -- helps reviewers scope the blast radius
6. **Progress tracker** -- table with links to stage files
7. **Execution protocol** -- instructions for the autonomous agent (use the template)
8. **Issues & Decisions** -- empty sections for runtime findings

### Writing stage files

Each stage file must be:

- **Independently testable** -- can verify without completing later stages
- **Committable** -- leaves codebase in a working state
- **Logically cohesive** -- groups related changes together
- **Self-contained** -- an agent reading only this file + index can implement it

Each stage contains:

- **Goal** -- one sentence
- **Dependencies** -- which stages must be DONE first
- **Steps** -- specific, actionable, testable (include file paths, line refs, exact values)
- **Verification** -- concrete commands with expected outcomes
- **Commit message** -- conventional commit format

### Writing resources

The `resources/` directory holds any shared reference material that stages need.
It is **not** prescriptive -- add whatever files the plan requires. Common examples:

- **queries.md** -- investigation queries (SQL, GraphQL, API calls, etc.)
- **commands.md** -- build, test, deploy, and pipeline execution commands
- **configs.md** -- reference configurations, environment variables, feature flags
- **data.md** -- sample data, test fixtures, seed values
- **api-reference.md** -- endpoint specs, request/response examples
- **migration.md** -- database migration steps, schema change scripts

Use placeholders (e.g., `{schema}`, `{env}`, `${API_URL}`) for portability
across environments. Only create resource files the plan actually needs.

### Stage design principles

1. **Logical dependencies** -- Stage 2 depends on Stage 1 explicitly
2. **Incremental value** -- each stage adds usable functionality, not just "setup"
3. **Clear boundaries** -- no overlap between stages
4. **One stage = one commit** -- never batch multiple stages

### Tips

- **Phase grouping**: If stages form logical phases (e.g., Phase A: sandbox validation,
  Phase B: corporate benchmarks), note this in the index.md strategy section and
  the progress tracker. But keep individual stage files -- the agent processes one at a time.
- **Plan families**: When plans form a series (36, 36b, 36c, ...), link predecessors
  in the index metadata. Shared investigation queries can reference a parent plan's
  resources directory.
- **Living documents**: Plans evolve. The autonomous agent updates the progress tracker
  and adds notes. Issues and decisions sections capture runtime findings.
  The user may also revise stages between agent runs.
