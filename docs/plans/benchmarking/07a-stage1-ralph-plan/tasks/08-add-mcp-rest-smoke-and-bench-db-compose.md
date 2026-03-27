# Task 08: Add MCP And REST Smoke Transports Plus Isolated Benchmark DB Compose

Dependencies: 05, 06

## Objective

Add non-primary transport coverage and isolated database support without confusing them with the benchmark-scored Stage 1 path.

## Required Changes

- Extend `benchmarks/adapters/neocortex_adapter.py` to support MCP and REST smoke modes.
- Use NeoCortex’s real MCP HTTP client pattern for MCP transport.
- Parse the real ingestion API response shape for REST transport.
- Document clearly in code and docs that MCP and REST are smoke and integration transports only in Stage 1.
- Add `benchmarks/docker-compose.bench.yml` with the correct NeoCortex database environment variable names.

## Constraints

- Do not treat MCP or REST as valid full LongMemEval scored transports unless the implementation can prove per-question isolation.
- Do not rely on `POSTGRES_DB` for the Python config path. Use the env names that the actual config model reads.
- Keep the compose extension safe to run alongside the normal development DB.

## Verification

- `docker compose -f docker-compose.yml -f benchmarks/docker-compose.bench.yml config`
- If Docker is available, `docker compose -f docker-compose.yml -f benchmarks/docker-compose.bench.yml up -d postgres-bench`
- Add at least one smoke test each for MCP and REST transport wiring.
- `uv run ruff check benchmarks`

## Completion Rule

Mark this task complete only when the transport smoke paths are wired correctly and the compose extension uses the real config contract.
