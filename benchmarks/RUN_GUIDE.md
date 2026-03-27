# Benchmark Run Guide

This guide explains how to run the Stage 1 LongMemEval benchmark in this repo.

## Scope

- Stage 1 scored runs use `direct` transport only.
- `mcp` and `rest` are smoke-only transports in Stage 1.
- The benchmark branch is expected to be `feat/benchmarking-skeleton`.

## Prerequisites

From the repository root:

```bash
uv sync
uv run python benchmarks/download_datasets.py
```

That installs dependencies and downloads or verifies the pinned LongMemEval-S dataset.

## No-Cost Smoke Run

Use this for the main acceptance-path smoke check:

```bash
NEOCORTEX_MOCK_DB=true uv run python -m benchmarks.runners.pipeline \
  --benchmark longmemeval \
  --transport direct \
  --judge-model mock \
  --answer-model mock \
  --run-id my-smoke-1 \
  --limit 5 \
  --mock-db
```

Notes:

- Use a fresh `--run-id`.
- Reusing the same `--run-id` without `--resume` fails by design.
- This exercises direct transport, question isolation, checkpointing, judging, and report generation.

## Resume an Interrupted Run

If a run stops mid-way, rerun the exact same command with `--resume`:

```bash
NEOCORTEX_MOCK_DB=true uv run python -m benchmarks.runners.pipeline \
  --benchmark longmemeval \
  --transport direct \
  --judge-model mock \
  --answer-model mock \
  --run-id my-smoke-1 \
  --limit 5 \
  --mock-db \
  --resume
```

Resume is per-question. Completed questions are skipped.

## Paid Validation Run

Use this to verify the real answer-model and judge-model path with minimal cost:

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
- Keep `--limit` low, usually `1` to `3`.

## Run Against Isolated Benchmark Postgres

Start the dedicated benchmark database:

```bash
docker compose -f docker-compose.yml -f benchmarks/docker-compose.bench.yml up -d postgres-bench
```

Then run the pipeline against it:

```bash
export POSTGRES_PORT=5433
export POSTGRES_DATABASE=neocortex_bench

uv run python -m benchmarks.runners.pipeline \
  --benchmark longmemeval \
  --transport direct \
  --judge-model mock \
  --answer-model mock \
  --run-id pg-smoke-1 \
  --limit 5
```

## Optional MCP / REST Smoke Services

These are not scored benchmark paths. They are only for transport smoke/integration work:

```bash
docker compose -f docker-compose.yml -f benchmarks/docker-compose.bench.yml --profile bench up -d \
  postgres-bench \
  neocortex-mcp-bench \
  neocortex-ingestion-bench
```

Ports:

- MCP HTTP: `8010`
- Ingestion HTTP: `8011`
- Postgres: `5433`

## Output Artifacts

Each run writes to:

```bash
benchmarks/reports/results/<run-id>/
```

Files to expect:

- `run_state.json`
- `summary_inputs.json`
- `summary.json`
- `report.md`
- `failures.jsonl`
- `questions/<question-id>.json`

## Inspect Results

Examples:

```bash
jq '.' benchmarks/reports/results/my-smoke-1/summary.json
sed -n '1,220p' benchmarks/reports/results/my-smoke-1/report.md
head -n 5 benchmarks/reports/results/my-smoke-1/failures.jsonl
jq '.' benchmarks/reports/results/my-smoke-1/questions/<question-id>.json
```

When debugging a bad result, inspect:

- `generated_answer`
- `judge_verdict`
- `retrieved_context`
- `metadata.search_result_metadata`
- `metadata.episode_ids`

## Quick Verification

```bash
uv run pytest benchmarks/tests -v
uv run ruff check benchmarks
test -f benchmarks/reports/results/my-smoke-1/summary.json
```

## Transport Smoke Tests

For MCP / REST smoke coverage:

```bash
uv run pytest benchmarks/tests/test_neocortex_adapter.py -v
```
