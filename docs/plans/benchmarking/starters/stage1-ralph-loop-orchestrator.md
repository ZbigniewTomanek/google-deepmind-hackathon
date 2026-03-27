/create_plan_v2

## Task

Act as the observer/orchestrator for a Ralph loop implementing the Stage 1 benchmarking plan.

The plan to implement is:

- `docs/plans/benchmarking/07a-stage1-ralph-plan/README.md`
- `docs/plans/benchmarking/WAYS_OF_WORKING.md`

The Ralph loop should execute that plan via:

```bash
./run_ralph_loop.sh docs/plans/benchmarking/07a-stage1-ralph-plan
```

## Role

This Codex instance is **not** the worker inside the loop. It is the observer outside the loop.

Think of this role as a human standing next to the loop:
- start the Ralph loop in a separate session,
- check progress every 3-5 minutes,
- note what changed,
- verify whether the loop appears healthy or stuck,
- do not interrupt or redirect the loop unless it is clearly broken or blocked.

The orchestrator is **on the loop, not in the loop**.

## Expected Behavior

1. Start the Ralph loop in a separate terminal/session.
2. Let it continue running autonomously.
3. Every 3-5 minutes:
   - inspect the plan README,
   - inspect git diff / changed files,
   - inspect whether task statuses are advancing,
   - note progress in concise observer notes.
4. Do **not** modify the benchmark implementation yourself while the loop is actively working.
5. Do **not** stop the Ralph loop just because a task is large or progress is slow.
6. Only intervene if there is a clear problem, such as:
   - the loop is repeatedly failing the same task,
   - the loop has crashed,
   - the loop is editing files outside the intended scope,
   - the loop is clearly violating the plan's corrected benchmark methodology.

## Observation Priorities

When checking in, pay attention to:

- whether the loop is implementing the correct plan:
  - `docs/plans/benchmarking/07a-stage1-ralph-plan/README.md`
- whether the loop is respecting the benchmarking ways of working:
  - `docs/plans/benchmarking/WAYS_OF_WORKING.md`
- whether task completion in the README matches actual code changes,
- whether the loop preserves the key Stage 1 constraints:
  - LongMemEval questions must be isolated per question,
  - Stage 1 scored path is `direct` transport,
  - MCP/REST are smoke-only,
  - answer model and judge model stay separate,
  - resume semantics are per-question,
  - `src/neocortex/` should not be modified as part of this benchmarking plan.

## Output Style

At each check-in, write short observer notes containing:

- current Ralph status,
- current task believed to be in progress,
- files changed since last check,
- whether the work appears on-track / risky / blocked,
- whether intervention is needed.

Keep these notes concise and factual.

## If The Loop Finishes

When the Ralph loop completes:

1. Confirm all tasks in `docs/plans/benchmarking/07a-stage1-ralph-plan/README.md` are marked complete.
2. Inspect the resulting changes and summarize what was implemented.
3. Note any gaps between the finished implementation and the plan.
4. Do not rewrite the implementation unless explicitly asked.

## Important Constraint

The plan being implemented is the corrected Ralph plan, not the older oversized implementation document.

Use:
- `docs/plans/benchmarking/07a-stage1-ralph-plan/README.md`
- `docs/plans/benchmarking/WAYS_OF_WORKING.md`

Do not use as the execution source of truth:
- `docs/plans/benchmarking/07a-stage1-implementation.md`
