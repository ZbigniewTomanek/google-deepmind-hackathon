# Task 09: Add End-To-End Tests And Benchmark Operator Docs

Dependencies: 07, 08

## Objective

Finish Stage 1 with reliable automated coverage and operator documentation that explains exactly what is supported.

## Required Changes

- Expand `benchmarks/tests/` to cover:
  - loader behavior,
  - judge behavior,
  - direct adapter behavior,
  - checkpoint and resume behavior,
  - full mock-db smoke run.
- Complete `benchmarks/README.md` with setup, download, smoke, and real-run instructions.
- State the Stage 1 limitation explicitly:
  - direct transport is the scored benchmark path,
  - MCP and REST are smoke-only,
  - no changes to `src/neocortex/` are required.
- Document a small paid-model validation command for 1-3 questions, separate from the no-cost smoke path.
- Include the expected output files and how to inspect failures.

## Constraints

- Keep the smoke test cheap. It should not require paid API calls.
- Avoid documentation that implies network transports are benchmark-correct if they are not.
- Prefer explicit commands over vague prose.

## Verification

- `uv run pytest benchmarks/tests -v`
- `NEOCORTEX_MOCK_DB=true uv run python -m benchmarks.runners.pipeline --benchmark longmemeval --transport direct --judge-model mock --answer-model mock --run-id final-smoke --limit 5 --mock-db`
- If API keys are available, run a 1-3 question real-model validation via the documented command and confirm normal artifacts are produced.
- Confirm `benchmarks/reports/results/final-smoke/summary.json` exists.
- `uv run ruff check benchmarks`

## Completion Rule

Mark this task complete only when the benchmark harness has passing smoke coverage and the docs tell an operator exactly how to run Stage 1 correctly.
