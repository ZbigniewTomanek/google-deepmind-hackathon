/create_plan_v2

## Task
Create a detailed implementation plan for the NeoCortex benchmarking skeleton (Stage 1 from `docs/plans/benchmarking/07-benchmarking-plan.md`).

## Context
- Branch: `feat/benchmarking-skeleton` (already created, synced with main)
- Ways of working: `docs/plans/benchmarking/WAYS_OF_WORKING.md`
- High-level roadmap: `docs/plans/benchmarking/07-benchmarking-plan.md`
- NeoCortex API surface: `src/neocortex/db/protocol.py` (MemoryRepository — 6 methods), MCP tools in `src/neocortex/tools/` (remember, recall, discover), REST ingestion in `src/neocortex/ingestion/routes.py`
- Test patterns to follow: `tests/mcp/test_tools.py`, `tests/test_ingestion_api.py`

## Scope — Stage 1 only
Build the Python benchmarking skeleton with LongMemEval (P0) as the first benchmark.

### Phase 0 — Verify NeoCortex runs (prerequisite, do this FIRST)
Before writing any benchmark code, confirm the system actually works:
- `uv sync` succeeds
- `uv run pytest tests/ -v` passes (unit tests, no Docker)
- `docker compose up -d postgres` starts PostgreSQL
- `uv run python -m neocortex` starts the MCP server against real DB
- `NEOCORTEX_MOCK_DB=true uv run python -m neocortex` starts with mock DB
- `NEOCORTEX_MOCK_DB=true uv run python -m neocortex.ingestion` starts the ingestion API
- Manually call `remember` + `recall` via the TUI or fastmcp client to confirm the round-trip works
If anything fails, fix it before proceeding. Benchmarking a broken system is pointless.

### Phase 1 — Skeleton implementation
1. `benchmarks/` directory structure with all modules
2. `MemoryProvider` protocol + NeoCortex adapter (3 transport options: MCP, REST, direct protocol)
3. Dataset downloader for LongMemEval (HuggingFace: `xiaowu0162/longmemeval-cleaned`, 500 questions, ~115K tokens per instance)
4. LongMemEval loader (parse questions into 5 categories: extraction, multi-session reasoning, temporal, knowledge updates, abstention)
5. Pipeline orchestrator with 7 checkpointed phases (setup → ingest → index → query → answer → evaluate → report)
6. LLM judge (GPT-4o, matching LongMemEval's `evaluate_qa.py` methodology)
7. F1 scorer (token-level, for cross-reference)
8. Report generator (summary.json + report.md + failures.jsonl)
9. Docker compose extension for isolated benchmark DB
10. Smoke test: pipeline end-to-end with mock DB + mock judge

## Constraints
- Read WAYS_OF_WORKING.md before planning — it has hard rules (always production PG for real runs, pin dataset versions with SHA256, checkpoint all phases, preserve failure evidence)
- Adapter must match MemoryBench's Provider interface shape (so Track A/B stay interchangeable)
- Follow existing test patterns from `tests/` (pytest, async fixtures, Pydantic models)
- Never modify `src/neocortex/` from benchmarking — if the system needs changes, that's a separate PR
- Output plan to `docs/plans/benchmarking/07a-stage1-implementation.md`
