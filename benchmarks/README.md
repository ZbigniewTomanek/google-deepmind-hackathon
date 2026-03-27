# Benchmarks

Stage 1 benchmarking lives under `benchmarks/` and targets LongMemEval-S on NeoCortex.

## Stage 1 support boundary

- `direct` is the only benchmark-scored transport in Stage 1.
- `mcp` and `rest` are smoke and integration transports only.
- The pipeline runner enforces this boundary and rejects `--transport mcp` or `--transport rest`.
- Stage 1 does not require any changes under `src/neocortex/`.

Why: only the direct path can give the harness a deterministic per-question NeoCortex identity, which is required to isolate each LongMemEval question to its own memory scope.

## Prerequisites

- Install dependencies: `uv sync`
- Download or verify the pinned dataset: `uv run python benchmarks/download_datasets.py`
- Optional refresh of the pinned artifact: `uv run python benchmarks/download_datasets.py --refresh`

The dataset lock is committed in code. The local dataset file and run artifacts stay under gitignored paths:

- `benchmarks/datasets/longmemeval/`
- `benchmarks/reports/results/`

## Main entry points

- `uv run python -m benchmarks`
- `uv run python -m benchmarks.runners.pipeline`
- `uv run python benchmarks/download_datasets.py`

`python -m benchmarks` is just a thin alias for the pipeline runner.

## No-cost smoke run

Use this command for the Stage 1 acceptance smoke path. It exercises the real direct adapter, per-question isolation, checkpointing, judging, and report generation without paid model calls:

```bash
NEOCORTEX_MOCK_DB=true uv run python -m benchmarks.runners.pipeline \
  --benchmark longmemeval \
  --transport direct \
  --judge-model mock \
  --answer-model mock \
  --run-id final-smoke \
  --limit 5 \
  --mock-db
```

Expected result: `benchmarks/reports/results/final-smoke/summary.json` exists and reports `transport: "direct"` with `pending: 0`.

To resume an interrupted run, rerun the same command with `--resume`:

```bash
NEOCORTEX_MOCK_DB=true uv run python -m benchmarks.runners.pipeline \
  --benchmark longmemeval \
  --transport direct \
  --judge-model mock \
  --answer-model mock \
  --run-id final-smoke \
  --limit 5 \
  --mock-db \
  --resume
```

Resume is per-question. Completed questions are skipped; failed or incomplete questions are retried.

## Paid-model validation

Use a tiny direct-path validation run to prove the real answer-generation and judge stack works end to end. Keep this to `--limit 1` through `--limit 3`.

```bash
NEOCORTEX_MOCK_DB=true uv run python -m benchmarks.runners.pipeline \
  --benchmark longmemeval \
  --transport direct \
  --answer-model gpt-4.1-mini \
  --judge-model gpt-4o-mini \
  --run-id validation-1q \
  --limit 1 \
  --mock-db
```

Requirements:

- `OPENAI_API_KEY` must be set.
- The dataset must already be present locally.

This is separate from the no-cost smoke path. Do not use MCP or REST for scored or validation benchmark runs.

## Running against the isolated benchmark Postgres

For a real database run, start the dedicated benchmark database instead of sharing the default developer DB:

```bash
docker compose -f docker-compose.yml -f benchmarks/docker-compose.bench.yml up -d postgres-bench
```

For local Python runs against that database:

```bash
export POSTGRES_PORT=5433
export POSTGRES_DATABASE=neocortex_bench
uv run python -m benchmarks.runners.pipeline \
  --benchmark longmemeval \
  --transport direct \
  --judge-model mock \
  --answer-model mock \
  --run-id pg-smoke \
  --limit 5
```

Optional bench-only HTTP services are available for smoke and integration work:

```bash
docker compose -f docker-compose.yml -f benchmarks/docker-compose.bench.yml --profile bench up -d \
  postgres-bench \
  neocortex-mcp-bench \
  neocortex-ingestion-bench
```

Ports from the bench override:

- MCP HTTP: `8010`
- Ingestion HTTP: `8011`
- Postgres: `5433`

These services are for transport smoke coverage only. They are not the benchmark-scored Stage 1 path.

## Expected artifacts

Each run writes to `benchmarks/reports/results/<run-id>/`.

Files to expect:

- `run_state.json`: checkpoint state for resume.
- `summary_inputs.json`: normalized inputs used to build reports.
- `summary.json`: machine-readable top-level result summary.
- `report.md`: human-readable report.
- `failures.jsonl`: one JSON object per incorrect answer or execution failure.
- `questions/<question-id>.json`: per-question execution record with retrieved context and metadata.

## Inspecting failures

Useful commands:

```bash
sed -n '1,220p' benchmarks/reports/results/<run-id>/report.md
jq '.' benchmarks/reports/results/<run-id>/summary.json
head -n 5 benchmarks/reports/results/<run-id>/failures.jsonl
jq '.' benchmarks/reports/results/<run-id>/questions/<question-id>.json
```

When a question is wrong, inspect:

- `generated_answer`
- `judge_verdict`
- `retrieved_context`
- `metadata.search_result_metadata`
- `metadata.episode_ids`

## Smoke coverage for MCP and REST transports

Network transports remain covered by tests, not by the scored benchmark runner:

```bash
uv run pytest benchmarks/tests/test_neocortex_adapter.py -v
```

Those tests exercise:

- direct question-scope isolation,
- MCP streamable-HTTP smoke behavior,
- REST ingestion plus MCP recall smoke behavior.

## Quick verification checklist

```bash
uv run pytest benchmarks/tests -v
uv run ruff check benchmarks
test -f benchmarks/reports/results/final-smoke/summary.json
```
