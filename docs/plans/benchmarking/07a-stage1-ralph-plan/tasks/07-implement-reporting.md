# Task 07: Implement Report Generation And Diagnostic Outputs

Dependencies: 06

## Objective

Turn per-question results into stable benchmark outputs that are useful both for score reporting and debugging.

## Required Changes

- Add `benchmarks/reports/generator.py`.
- Emit `summary.json`, `report.md`, and `failures.jsonl` under `benchmarks/reports/results/<run-id>/`.
- Summarize overall accuracy, per-category accuracy, latency, context size, and runtime.
- Preserve enough failure context to explain why a question failed.
- If the pipeline preserves retrieval provenance cheaply, include it in failure diagnostics. Do not expand scope into a full retrieval-metric implementation if it complicates Stage 1.

## Constraints

- Reports must distinguish `answer_model` and `judge_model`.
- Reports must include the dataset identity and NeoCortex git SHA when available.
- `failures.jsonl` should stay machine-readable and one-record-per-line.

## Verification

- Run a small mock benchmark and confirm the three output files are created.
- `uv run python -c "import json, pathlib; p = pathlib.Path('benchmarks/reports/results/smoke-runner/summary.json'); print(json.loads(p.read_text())['benchmark'])"`
- `uv run ruff check benchmarks/reports`

## Completion Rule

Mark this task complete only when a completed mock run produces stable report artifacts with enough detail to debug incorrect answers.
