# Plan 07 — Benchmarking Skeleton

**Status:** Draft
**Branch:** `feat/benchmarking-skeleton`
**Goal:** Build a reproducible benchmarking harness that deploys NeoCortex locally and runs the same benchmarks competitors use — producing comparable metrics for evidence and diagnostics.

---

## 1. Benchmark Selection & Rationale

Three industry-standard benchmarks, prioritized by relevance to our knowledge-graph architecture:

| Priority | Benchmark | Paper | Dataset | Why |
|----------|-----------|-------|---------|-----|
| **P0** | **LongMemEval** | [ICLR 2025](https://arxiv.org/abs/2410.10813) | [HuggingFace](https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned) | Most rigorous. Tests 5 abilities (extraction, multi-session reasoning, temporal, knowledge updates, abstention). Used by Zep (71.2%) and Supermemory (81.6%). Knowledge updates & temporal reasoning directly exercise our graph advantages. |
| **P1** | **LoCoMo** | [ACL 2024](https://arxiv.org/abs/2402.17753) | [GitHub](https://github.com/snap-research/locomo) `data/locomo10.json` | Industry standard — Mem0 (66.9%), Letta, OpenViking, MemMachine all report here. 10 multi-session conversations with single-hop, multi-hop, temporal, adversarial QA. |
| **P2** | **ConvoMem** | [arXiv 2511.10523](https://arxiv.org/abs/2511.10523) | [HuggingFace](https://huggingface.co/datasets/Salesforce/ConvoMem) | Largest (75K QA pairs, 100 personas). Tests personalization & preference learning at variable context sizes. CC-BY-NC-4.0 license (non-commercial). |

**Skip:** DMR (MemGPT) — too easy (94-98% trivially).

### Competitor Reference Scores

| System | LongMemEval | LoCoMo | ConvoMem |
|--------|-------------|--------|----------|
| Supermemory | 81.6% | #1 (exact unreported) | #1 (exact unreported) |
| Zep/Graphiti | 71.2% | — | — |
| Mem0 | — | 66.9% (LLM-judge) | — |
| OpenViking | — | 52.08% (completion rate) | — |
| Letta | — | 74.0% (GPT-4o-mini) | — |

**Metric inconsistency warning:** Mem0 uses LLM-as-judge on LoCoMo; the original paper uses F1. OpenViking reports task completion rate, not QA accuracy. We should report **both** F1 and LLM-as-judge for LoCoMo to enable comparison with either camp.

---

## 2. Architecture

### Two-Track Approach

**Track A — MemoryBench adapter (competitive comparison):**
Write a ~100-line TypeScript provider for [Supermemory's MemoryBench](https://github.com/supermemoryai/memorybench) that calls NeoCortex over HTTP. Gives immediate apples-to-apples MemScore (`accuracy% / latencyMs / contextTokens`) against Supermemory, Mem0, Zep.

**Track B — Python benchmarking skeleton (diagnostics & control):**
Native Python harness for deeper analysis — per-query failure categorization, graph quality metrics, component-level profiling. This is the primary deliverable.

### Python Skeleton Layout

```
benchmarks/
  README.md                    # How to run, interpret results
  conftest.py                  # Shared pytest fixtures (NeoCortex client, dataset loaders)
  datasets/                    # Downloaded benchmark data (gitignored)
    longmemeval/
    locomo/
    convomem/
  download_datasets.py         # Script to fetch all datasets
  adapters/
    neocortex_adapter.py       # MemoryProvider protocol implementation for NeoCortex
    base.py                    # Abstract MemoryProvider protocol
  benchmarks/
    longmemeval.py             # LongMemEval loader + runner
    locomo.py                  # LoCoMo loader + runner
    convomem.py                # ConvoMem loader + runner (stretch)
  judges/
    llm_judge.py               # LLM-as-judge evaluator (GPT-4o / Claude)
    f1_judge.py                # Token-level F1 scorer (LoCoMo standard)
  runners/
    pipeline.py                # Orchestrator: ingest → wait → query → answer → evaluate → report
    checkpoint.py              # Resume-friendly phase checkpointing
  reports/
    generator.py               # Markdown + JSON report output
    results/                   # Timestamped run outputs (gitignored)
  docker-compose.bench.yml     # Extends main docker-compose for benchmark runs
```

### MemoryProvider Protocol (what the adapter implements)

```python
class MemoryProvider(Protocol):
    async def initialize(self) -> None: ...
    async def ingest_sessions(self, sessions: list[Session]) -> IngestResult: ...
    async def await_indexing(self, result: IngestResult) -> None: ...
    async def search(self, query: str, limit: int = 10) -> list[SearchResult]: ...
    async def clear(self) -> None: ...
```

The NeoCortex adapter calls `store_episode` (via MCP or REST) for ingestion and `recall` for search. This matches the MemoryBench provider interface 1:1, making Track A/B interchangeable at the data level.

---

## 3. Benchmark Pipeline (per benchmark run)

```
1. SETUP      — docker compose up (PostgreSQL + NeoCortex)
2. INGEST     — load dataset sessions → adapter.ingest_sessions()
3. INDEX      — adapter.await_indexing() (poll until ready)
4. QUERY      — for each question: adapter.search(query) → context
5. ANSWER     — LLM generates answer from retrieved context
6. EVALUATE   — judge scores answer vs ground truth
7. REPORT     — aggregate by category, compute metrics, write report
```

Each phase checkpoints to `benchmarks/reports/results/{run_id}/` so failed runs resume.

### Metrics Collected

| Metric | Source | Purpose |
|--------|--------|---------|
| Accuracy (per category) | LLM judge | Primary quality metric |
| F1 score | Token overlap | LoCoMo standard metric |
| Latency (p50, p95, p99) | Timer around search() | Performance |
| Context tokens | tiktoken count on search results | Efficiency |
| Ingestion throughput | Episodes/sec during ingest | Capacity |
| Memory usage | Docker stats | Resource profiling |

### Report Output

Each run produces:
- `summary.json` — machine-readable results
- `report.md` — human-readable with tables, per-category breakdowns, failure examples
- `failures.jsonl` — every incorrect answer with question, expected, actual, retrieved context (for debugging)

---

## 4. Workflow: Running Benchmarks on Latest Code

Since this is a fast-moving project, benchmarks must always run against the latest `main`:

```bash
# 1. Switch to benchmark branch and pull latest main
git checkout feat/benchmarking-skeleton
git pull origin main

# 2. Rebuild and start services
docker compose -f docker-compose.yml -f benchmarks/docker-compose.bench.yml up -d --build

# 3. Run a specific benchmark
uv run python -m benchmarks.runners.pipeline \
  --benchmark longmemeval \
  --judge gpt-4o \
  --run-id "$(date +%Y%m%d-%H%M%S)" \
  --limit 50  # optional: subset for quick iteration

# 4. View results
cat benchmarks/reports/results/<run-id>/report.md
```

For CI integration (future): a GitHub Action on `main` push triggers benchmark runs and posts MemScore to PR comments.

---

## 5. Implementation Stages

### Stage 1 — Skeleton & LongMemEval (P0)

- [ ] Create `benchmarks/` directory structure
- [ ] Write `MemoryProvider` protocol and NeoCortex adapter
- [ ] Write `download_datasets.py` (LongMemEval from HuggingFace)
- [ ] Implement LongMemEval loader (parse 500 questions, extract sessions)
- [ ] Implement pipeline orchestrator (ingest → query → answer → evaluate)
- [ ] Implement LLM judge (GPT-4o, matching LongMemEval eval script)
- [ ] Implement F1 scorer (token-level, for cross-reference)
- [ ] Write report generator (per-category accuracy table + failures JSONL)
- [ ] Docker compose extension for isolated benchmark DB
- [ ] End-to-end test: run LongMemEval-S against mock DB, verify pipeline completes

**Exit criteria:** `uv run python -m benchmarks.runners.pipeline --benchmark longmemeval` produces a valid report with per-category accuracy scores.

### Stage 2 — LoCoMo (P1)

- [ ] Implement LoCoMo loader (parse `locomo10.json`, extract sessions + QA pairs)
- [ ] Add F1-score evaluation (LoCoMo standard)
- [ ] Add LLM-as-judge evaluation (Mem0 variant, for comparison)
- [ ] Report both metrics side-by-side

**Exit criteria:** LoCoMo report with F1 and LLM-judge scores, comparable to Mem0/Letta published numbers.

### Stage 3 — MemoryBench Adapter (Track A)

- [ ] Fork/clone `supermemoryai/memorybench`
- [ ] Write `src/providers/neocortex/index.ts` implementing Provider interface
- [ ] Register in provider index, add to ProviderName union type
- [ ] Validate: `bun run src/index.ts run -p neocortex -b longmemeval -j gpt-4o`
- [ ] Compare: `bun run src/index.ts compare -p neocortex,supermemory -b longmemeval`

**Exit criteria:** MemoryBench produces MemScore for NeoCortex alongside Supermemory/Mem0/Zep.

### Stage 4 — ConvoMem & Diagnostics (P2, stretch)

- [ ] Implement ConvoMem loader (HuggingFace dataset, 6 evidence categories)
- [ ] Add scaling analysis (accuracy vs context size: 1, 10, 50, 100, 150, 300 conversations)
- [ ] Add graph-specific diagnostics (not covered by any standard benchmark):
  - Entity resolution accuracy (are duplicates merged?)
  - Relationship extraction quality (are edges correct?)
  - Temporal edge validity (are superseded facts handled?)
  - Multi-hop traversal success rate

---

## 6. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| StubProcessor stores raw text — no entity extraction yet | Low recall on graph-dependent questions | Benchmark both episode-only recall and graph-enhanced recall (when extraction lands). Document the gap explicitly. |
| Mock DB uses substring matching | Meaningless benchmark results | **Always** run benchmarks against production PostgreSQL (Level 4). Mock only for pipeline smoke tests. |
| LLM judge costs ($) | ~$5-15 per full LongMemEval run with GPT-4o | Use `--limit N` for iteration. Cache judge results in checkpoints. Consider Claude Haiku for cheap re-runs. |
| Metric inconsistency across competitors | Misleading comparisons | Report both F1 and LLM-judge for LoCoMo. Document which metric each competitor uses. |
| Datasets may update (LongMemEval-cleaned, etc.) | Results not reproducible | Pin dataset versions in `download_datasets.py`. Record SHA256 of downloaded files. |

---

## 7. Key References

- [MemoryBench repo](https://github.com/supermemoryai/memorybench) — Supermemory's harness (TypeScript/Bun)
- [LongMemEval repo](https://github.com/xiaowu0162/LongMemEval) — eval scripts + data
- [LoCoMo repo](https://github.com/snap-research/locomo) — dataset + eval
- [ConvoMem repo](https://github.com/SalesforceAIResearch/ConvoMem) — code + dataset
- [Zep paper](https://arxiv.org/abs/2501.13956) — LongMemEval methodology details
- [Mem0 paper](https://arxiv.org/abs/2504.19413) — LoCoMo methodology details
- [Letta benchmarking blog](https://www.letta.com/blog/benchmarking-ai-agent-memory) — critical perspective on metric comparisons
- `docs/research/06-openviking-documentation.md` — OpenViking LoCoMo results (local)
- `docs/research/03-competitive-analysis-and-swot.md` — competitive landscape (local)
