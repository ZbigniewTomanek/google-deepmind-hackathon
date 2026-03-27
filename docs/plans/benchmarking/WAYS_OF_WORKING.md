# Benchmarking — Ways of Working

This document defines how benchmarking work is done on the NeoCortex project. It is intended for both human contributors and AI agents working on benchmarking tasks in future conversations.

---

## Branch Strategy

Benchmarking lives on a **dedicated long-lived branch** (`feat/benchmarking-skeleton`) that regularly pulls from `main`. It is never merged back into `main` — it exists to evaluate `main`, not to change it.

### Why a Separate Branch

NeoCortex is a fast-moving hackathon project. The memory system (storage, recall, embeddings, scoring) changes frequently. Benchmarking must:
- Always test the **latest** production code from `main`
- Not pollute `main` with benchmark infrastructure, datasets, or results
- Be independently runnable without affecting the core development workflow

### Sync Workflow

Before every benchmark session:

```bash
git checkout feat/benchmarking-skeleton
git pull origin main
```

If there are merge conflicts in `src/neocortex/` (the code under test), resolve in favor of `main` — benchmarking adapts to the system, not the other way around.

### What Lives on This Branch

| On `feat/benchmarking-skeleton` | On `main` |
|--------------------------------|-----------|
| `benchmarks/` directory (harness, adapters, loaders, judges, reports) | `src/neocortex/` (the system being benchmarked) |
| `docs/plans/benchmarking/` (plans, ways of working) | `docs/plans/01-06` (feature plans) |
| Downloaded datasets (gitignored) | Tests (`tests/`) |
| Benchmark results (gitignored) | Docker config |

---

## Directory Structure

All benchmarking code lives under `benchmarks/` at the project root:

```
benchmarks/
  adapters/                  # MemoryProvider implementations
    base.py                  # Abstract protocol
    neocortex_adapter.py     # NeoCortex adapter (calls MCP/REST)
  benchmarks/                # Dataset loaders and question parsers
    longmemeval.py
    locomo.py
    convomem.py
  judges/                    # Answer evaluation
    llm_judge.py             # LLM-as-judge (GPT-4o / Claude)
    f1_judge.py              # Token-level F1 scorer
  runners/
    pipeline.py              # Main orchestrator
    checkpoint.py            # Phase-level checkpointing
  reports/
    generator.py             # Output formatting
    results/                 # Run outputs (gitignored)
  datasets/                  # Downloaded data (gitignored)
  download_datasets.py       # Dataset fetcher with version pinning
  docker-compose.bench.yml   # Extends main docker-compose
```

---

## Running Benchmarks

### Prerequisites

- Docker running (for PostgreSQL)
- `uv sync` completed
- API keys set: `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` (for LLM judge)
- Datasets downloaded: `uv run python benchmarks/download_datasets.py`

### Quick Run

```bash
# Full pipeline against latest main
git checkout feat/benchmarking-skeleton && git pull origin main
docker compose -f docker-compose.yml -f benchmarks/docker-compose.bench.yml up -d --build
uv run python -m benchmarks.runners.pipeline \
  --benchmark longmemeval \
  --judge gpt-4o \
  --run-id "$(date +%Y%m%d-%H%M%S)"
```

### Development / Iteration

```bash
# Limit to N questions for fast iteration
uv run python -m benchmarks.runners.pipeline \
  --benchmark longmemeval --limit 20 --judge gpt-4o --run-id dev-test

# Resume a failed run (checkpoints preserved)
uv run python -m benchmarks.runners.pipeline \
  --benchmark longmemeval --judge gpt-4o --run-id dev-test --resume
```

### Smoke Test (no Docker, no LLM costs)

```bash
# Runs pipeline with mock DB and mock judge — validates wiring only
NEOCORTEX_MOCK_DB=true uv run python -m benchmarks.runners.pipeline \
  --benchmark longmemeval --judge mock --run-id smoke --limit 5
```

---

## Key Principles

### 1. Always Benchmark Against Production PostgreSQL

The mock DB (`InMemoryRepository`) uses substring matching. It will produce meaningless accuracy numbers. Use it **only** for pipeline smoke tests to verify the harness wiring works.

Real benchmarks must use the full production stack: PostgreSQL with pgvector, BM25 (tsvector), graph traversal, and the `GraphServiceAdapter`.

### 2. Report Multiple Metrics

Competitors use different metrics for the same benchmarks, making cross-system comparison unreliable. To maximize comparability:

- **LoCoMo:** Report both F1 (original paper standard) and LLM-as-judge (Mem0 variant)
- **LongMemEval:** Report LLM-as-judge accuracy per category (5 categories)
- **All benchmarks:** Always report latency (p50/p95/p99) and context token count alongside accuracy

### 3. Pin Dataset Versions

Datasets update over time (e.g., LongMemEval has a "cleaned" version from Sep 2025). `download_datasets.py` must:
- Pin exact URLs and versions
- Record SHA256 checksums of downloaded files
- Fail loudly if checksums don't match

### 4. Checkpoint Everything

The pipeline has 7 phases (setup, ingest, index, query, answer, evaluate, report). Each phase writes its output to `benchmarks/reports/results/{run_id}/`. If a run fails mid-evaluation (e.g., LLM API rate limit), it can resume from the last completed phase without re-ingesting or re-querying.

### 5. Preserve Failure Evidence

Every incorrect answer is written to `failures.jsonl` with:
- The question and its type/category
- The expected (ground truth) answer
- The system's actual answer
- The retrieved context that was used
- The judge's explanation for why it was marked incorrect

This is the primary diagnostic tool for identifying systemic weaknesses.

---

## NeoCortex Adapter Contract

The adapter bridges benchmark datasets to NeoCortex's API. It implements the `MemoryProvider` protocol:

```python
class MemoryProvider(Protocol):
    async def initialize(self) -> None: ...
    async def ingest_sessions(self, sessions: list[Session]) -> IngestResult: ...
    async def await_indexing(self, result: IngestResult) -> None: ...
    async def search(self, query: str, limit: int = 10) -> list[SearchResult]: ...
    async def clear(self) -> None: ...
```

**Mapping to NeoCortex:**

| MemoryProvider method | NeoCortex call | Notes |
|-----------------------|----------------|-------|
| `ingest_sessions()` | `POST /ingest/text` or `store_episode()` via MCP | One episode per session (concatenated messages) |
| `await_indexing()` | Poll until embeddings are computed | May be instant if synchronous |
| `search()` | `recall` MCP tool or `repo.recall()` | Returns ranked `RecallItem` list |
| `clear()` | Drop and recreate agent's graph schema | Via `SchemaManager` |

The adapter must be configurable to target either:
- **MCP transport** (via `fastmcp.Client`) — tests the full tool stack
- **REST transport** (via `httpx`) — tests the ingestion API path
- **Direct protocol** (via `MemoryRepository`) — lowest overhead, for profiling

---

## Metrics Reference

### MemScore (Supermemory's composite)

```
accuracy% / latencyMs / contextTokens
```

Not collapsed into a single number. We adopt this format for easy comparison with MemoryBench results.

### Per-Benchmark Metrics

**LongMemEval** — 5 category accuracy scores:
- Information Extraction, Multi-Session Reasoning, Knowledge Updates, Temporal Reasoning, Abstention

**LoCoMo** — 4 category scores (dual metric):
- Single-hop, Multi-hop, Temporal, Adversarial
- Report both F1 and LLM-judge accuracy

**ConvoMem** — 6 category scores:
- User Facts, Assistant Facts, Changing Facts, Abstention, Preferences, Implicit Connections

### Operational Metrics (all benchmarks)

| Metric | How | Why |
|--------|-----|-----|
| Search latency (p50/p95/p99) | Timer around `search()` | Performance regression detection |
| Context tokens per query | `tiktoken` count on returned results | Efficiency vs. competitors |
| Ingestion throughput | Episodes/sec during ingest phase | Capacity planning |
| Total run time | Wall clock for full pipeline | Budgeting |
| LLM judge cost | Token usage from judge API | Cost management |

---

## For AI Agents Working on Benchmarking

When starting a benchmarking session:

1. **Always sync first:** `git checkout feat/benchmarking-skeleton && git pull origin main`
2. **Read `docs/plans/benchmarking/07-benchmarking-plan.md`** for the implementation roadmap and current stage
3. **Read this document** for conventions and constraints
4. **Check `benchmarks/reports/results/`** for previous run outputs to understand current baseline
5. **Never modify `src/neocortex/`** from the benchmarking branch — if the system needs changes, those go through a separate PR to `main`

When implementing benchmark code:

- Follow the same patterns as `tests/` — use `pytest`, async fixtures, Pydantic models
- The adapter must work with both mock and production backends
- All new benchmark loaders must parse the canonical dataset format (don't transform datasets into custom formats)
- Judge prompts should match what competitors use (see LongMemEval's `evaluate_qa.py` and MemoryBench's `src/prompts/`)

When reporting results:

- Never claim scores without specifying: benchmark name, dataset version, metric type, judge model, and NeoCortex git SHA
- Include the `--limit` value if the run was on a subset
- Compare against published competitor scores only with matching metrics
