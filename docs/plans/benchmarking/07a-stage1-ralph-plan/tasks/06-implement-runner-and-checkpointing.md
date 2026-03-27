# Task 06: Implement Run-State Checkpointing And The Per-Question Pipeline Runner

Dependencies: 03, 04, 05

## Objective

Implement the real Stage 1 runner using the corrected execution model: each question runs in its own isolated scope, completed questions are checkpointed, and interrupted runs resume from the first incomplete question.

## Required Changes

- Add `benchmarks/runners/checkpoint.py`.
- Add `benchmarks/runners/pipeline.py`.
- Implement a run-state model that tracks per-question progress and result files.
- Add a CLI with at least `--benchmark`, `--run-id`, `--limit`, `--question-id`, `--resume`, `--transport`, `--mock-db`, `--answer-model`, and `--judge-model`.
- Enforce that scored LongMemEval runs use the direct adapter in Stage 1.
- Structure execution as:
  1. setup run metadata,
  2. for each selected question: isolate scope, ingest sessions, wait for indexing, search, answer, evaluate, persist question result,
  3. aggregate final summary inputs.

## Constraints

- Do not resurrect the invalid “ingest all questions, then query all questions” phase model.
- Resume behavior must be idempotent. Re-running the same `run_id` with `--resume` must not duplicate completed question work.
- The runner must not require MCP or REST to complete the benchmark-scored path.

## Verification

- `uv run python -m benchmarks.runners.pipeline --help`
- `NEOCORTEX_MOCK_DB=true uv run python -m benchmarks.runners.pipeline --benchmark longmemeval --transport direct --judge-model mock --answer-model mock --run-id smoke-runner --limit 3 --mock-db`
- Re-run the previous command with `--resume` and confirm completed questions are skipped.
- `uv run ruff check benchmarks/runners`

## Completion Rule

Mark this task complete only when the runner can finish a small mock-db run and resume cleanly without cross-question contamination.
