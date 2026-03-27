# Task 05: Implement The Direct NeoCortex Adapter With Question Isolation

Dependencies: 01, 03

## Objective

Build the Stage 1 benchmark-scored transport: a direct NeoCortex adapter that preserves current ingest and recall semantics while isolating each benchmark question into its own scope.

## Required Changes

- Add `benchmarks/adapters/base.py`.
- Add `benchmarks/adapters/neocortex_adapter.py`.
- Use `create_services()` and `shutdown_services()` for lifecycle management.
- Preserve current `remember` semantics by embedding stored text and updating episode embeddings when embeddings are available.
- Preserve current `recall` semantics by computing a query embedding before recall when embeddings are available.
- Add deterministic question-scope identity helpers derived from `run_id + question_id`.
- Ensure cleanup is safe and scoped. Do not rely on a nonexistent global admin clear endpoint.
- Add tests for mock-db ingest and recall through the direct adapter.

## Constraints

- The direct adapter is the only benchmark-scored Stage 1 path.
- Do not benchmark a degraded path that bypasses embeddings.
- Do not implement “clear all benchmark data” in a way that can damage unrelated developer data.
- If PostgreSQL cleanup is needed, scope it to the benchmark run or scoped agent identity only.

## Verification

- `uv run pytest benchmarks/tests -k 'adapter or direct' -v`
- `NEOCORTEX_MOCK_DB=true uv run python -c "import asyncio; from benchmarks.adapters.neocortex_adapter import smoke_check_direct; asyncio.run(smoke_check_direct())"`
- `uv run ruff check benchmarks/adapters benchmarks/tests`

## Completion Rule

Mark this task complete only when a single question can be ingested and queried through the direct adapter without leaking data across question scopes.
