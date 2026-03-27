# Stage 1 — Benchmarking Skeleton Implementation Plan

**Status:** Draft
**Branch:** `feat/benchmarking-skeleton`
**Parent plan:** `docs/plans/benchmarking/07-benchmarking-plan.md`
**Ways of working:** `docs/plans/benchmarking/WAYS_OF_WORKING.md`

---

## Overview

Build the Python benchmarking skeleton with LongMemEval (P0) as the first benchmark. This produces a reproducible pipeline that ingests conversation sessions into NeoCortex, queries against them, scores answers via an LLM judge, and generates per-category accuracy reports — comparable to published Zep (71.2%) and Supermemory (81.6%) results.

## Current State Analysis

- **NeoCortex core** is functional: `MemoryRepository` protocol at `src/neocortex/db/protocol.py:6` with two implementations (`InMemoryRepository` for tests, `GraphServiceAdapter` for production).
- **MCP tools** (`remember`, `recall`, `discover`) use the protocol via lifespan context.
- **REST ingestion** exposes `POST /ingest/text`, `/ingest/document`, `/ingest/events` at port 8001.
- **No benchmarking code exists** — `benchmarks/` directory does not exist yet.
- **Existing test patterns** use pytest + async fixtures + Pydantic models (`tests/mcp/test_tools.py`, `tests/test_ingestion_api.py`).
- **Docker** runs pgvector 0.8.0 on PG16 with init migrations auto-applied.

### Key Discoveries

- `MemoryRepository.store_episode()` at `db/protocol.py:9` takes `agent_id`, `content`, `context`, `source_type` and returns `episode_id: int`.
- `MemoryRepository.recall()` at `db/protocol.py:18` takes `query`, `agent_id`, `limit`, `query_embedding` and returns `list[RecallItem]`.
- `RecallItem` at `schemas/memory.py:14` has `item_id`, `name`, `content`, `item_type`, `score`, `source`, `source_kind`, `graph_name`.
- `InMemoryRepository` at `db/mock.py:15` does case-insensitive substring matching — meaningless for accuracy benchmarks (WAYS_OF_WORKING §1).
- `MCPSettings` at `mcp_settings.py:6` controls `mock_db`, `auth_mode`, `transport`, embedding model, hybrid recall weights.
- `create_services()` at `services.py:26` returns a `ServiceContext` TypedDict — the factory for both MCP and ingestion lifespans.
- LongMemEval `longmemeval_s_cleaned` split: 500 questions, ~80 sessions each, ~115K tokens. JSON array with fields: `question_id`, `question_type`, `question`, `answer`, `question_date`, `haystack_session_ids`, `haystack_dates`, `haystack_sessions`, `answer_session_ids`.
- LongMemEval has 6 `question_type` values mapping to 5 abilities: `single-session-user`, `single-session-assistant`, `single-session-preference` (Information Extraction), `multi-session` (Multi-Session Reasoning), `temporal-reasoning` (Temporal Reasoning), `knowledge-update` (Knowledge Updates). Abstention identified by `_abs` suffix on `question_id`.
- LongMemEval's `evaluate_qa.py` uses 5 prompt variants (default, temporal with off-by-one tolerance, knowledge-update with updated answer, preference with partial rubric, abstention with unanswerable detection). Binary yes/no scoring, temperature=0, max_tokens=10.

## Desired End State

```bash
# Smoke test (no Docker, no LLM costs) — validates full pipeline wiring
NEOCORTEX_MOCK_DB=true uv run python -m benchmarks.runners.pipeline \
  --benchmark longmemeval --judge mock --run-id smoke --limit 5

# Real benchmark run against production PG
docker compose -f docker-compose.yml -f benchmarks/docker-compose.bench.yml up -d
uv run python -m benchmarks.runners.pipeline \
  --benchmark longmemeval --judge gpt-4o --run-id "$(date +%Y%m%d-%H%M%S)"

# View results
cat benchmarks/reports/results/<run-id>/report.md
cat benchmarks/reports/results/<run-id>/summary.json
cat benchmarks/reports/results/<run-id>/failures.jsonl
```

**Verification:** `summary.json` contains per-category accuracy scores for all 5 LongMemEval categories. `failures.jsonl` contains every incorrect answer with full diagnostic context. The pipeline completes all 7 phases (setup → ingest → index → query → answer → evaluate → report) and can resume from any checkpoint.

## What We're NOT Doing

- **Stage 2+ benchmarks** (LoCoMo, ConvoMem) — only LongMemEval
- **MemoryBench TypeScript adapter** (Track A) — Stage 3
- **Graph-specific diagnostics** (entity resolution, relationship extraction) — Stage 4
- **CI integration** (GitHub Actions, PR comments) — future work
- **Modifying `src/neocortex/`** — if the system needs changes, that's a separate PR to `main`
- **Performance profiling** (memory usage, Docker stats) — operational metrics beyond latency are deferred

---

## Implementation Approach

Build bottom-up: base models first, then independent components (adapter, loader, judge), then the orchestrator that wires them together, finally the smoke test. Each phase is independently testable.

**Dependency graph:**
```
Phase 1 (scaffolding + models)
    ├──► Phase 2 (downloader)
    ├──► Phase 3 (adapter)
    └──► Phase 5 (judge + F1)
Phase 2 ──► Phase 4 (loader)
Phase 3 + Phase 4 + Phase 5 ──► Phase 6 (checkpoint + pipeline)
Phase 6 ──► Phase 7 (reporter)
Phase 7 ──► Phase 8 (docker-compose)
Phase 8 ──► Phase 9 (smoke test)
```

---

## Phase 0: Verify NeoCortex Runs

### Overview

Before writing any benchmark code, confirm the system actually works. Benchmarking a broken system is pointless.

### Verification Steps

Run each command and confirm it succeeds:

```bash
# 1. Install deps
uv sync

# 2. Unit tests (no Docker)
uv run pytest tests/ -v

# 3. Start PostgreSQL
docker compose up -d postgres

# 4. MCP server with real DB
uv run python -m neocortex
# Ctrl-C after it starts successfully

# 5. MCP server with mock DB
NEOCORTEX_MOCK_DB=true uv run python -m neocortex
# Ctrl-C after it starts successfully

# 6. Ingestion API with mock DB
NEOCORTEX_MOCK_DB=true uv run python -m neocortex.ingestion
# Ctrl-C after it starts successfully

# 7. Round-trip test via TUI or fastmcp client
# Call remember("Alice likes oolong tea") then recall("oolong")
# Confirm the stored memory is returned
```

### Success Criteria

#### Automated Verification:
- [ ] `uv sync` exits 0
- [ ] `uv run pytest tests/ -v` all tests pass
- [ ] `docker compose up -d postgres` container starts and is healthy

#### Manual Verification:
- [ ] MCP server starts on both mock and real DB
- [ ] Ingestion API starts on mock DB
- [ ] remember + recall round-trip returns stored memory

**If anything fails, fix it before proceeding to Phase 1.**

---

## Phase 1: Project Scaffolding + Base Models

### Overview

Create the `benchmarks/` directory structure, all `__init__.py` files, shared Pydantic models, and project configuration. This provides the type foundation all other phases depend on.

### Changes Required

#### 1. Directory structure

Create the full tree:

```
benchmarks/
  __init__.py
  __main__.py               # Entry point: python -m benchmarks (delegates to pipeline CLI)
  models.py                  # Shared Pydantic models
  adapters/
    __init__.py
    base.py                  # MemoryProvider protocol
    neocortex_adapter.py     # (Phase 3)
  benchmarks/
    __init__.py
    longmemeval.py           # (Phase 4)
  datasets/                  # Downloaded data (gitignored)
    .gitkeep
  download_datasets.py       # (Phase 2)
  judges/
    __init__.py
    llm_judge.py             # (Phase 5)
    f1_judge.py              # (Phase 5)
  runners/
    __init__.py
    pipeline.py              # (Phase 6)
    checkpoint.py            # (Phase 6)
  reports/
    __init__.py
    generator.py             # (Phase 7)
    results/                 # Run outputs (gitignored)
      .gitkeep
  docker-compose.bench.yml   # (Phase 8)
  conftest.py                # Shared pytest fixtures (Phase 9)
  README.md                  # How to run + interpret results
```

#### 2. `.gitignore` additions

**File**: `.gitignore` (append)

```gitignore
# Benchmarking
benchmarks/datasets/*
!benchmarks/datasets/.gitkeep
benchmarks/reports/results/*
!benchmarks/reports/results/.gitkeep
```

#### 3. Shared models

**File**: `benchmarks/models.py`

```python
"""Shared data models for the benchmarking harness."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# --- Dataset models ---

class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"


class SessionMessage(BaseModel):
    """A single turn in a conversation session."""
    role: MessageRole
    content: str
    has_answer: bool = False  # True if this turn contains evidence for the question


class Session(BaseModel):
    """A conversation session with metadata."""
    session_id: str
    messages: list[SessionMessage]
    timestamp: datetime | None = None


# --- Benchmark question models ---

class QuestionCategory(str, Enum):
    """LongMemEval's 5 memory ability categories."""
    INFORMATION_EXTRACTION = "information_extraction"
    MULTI_SESSION_REASONING = "multi_session_reasoning"
    TEMPORAL_REASONING = "temporal_reasoning"
    KNOWLEDGE_UPDATES = "knowledge_updates"
    ABSTENTION = "abstention"


class BenchmarkQuestion(BaseModel):
    """A single benchmark evaluation question."""
    question_id: str
    question: str
    question_type: str  # Raw type from dataset (e.g., "single-session-user")
    category: QuestionCategory  # Mapped ability category
    expected_answer: str
    question_date: str | None = None
    answer_session_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


# --- Adapter models ---

class IngestResult(BaseModel):
    """Result of ingesting sessions into a memory provider."""
    episode_ids: list[int] = Field(default_factory=list)
    sessions_ingested: int = 0
    errors: list[str] = Field(default_factory=list)


class SearchResult(BaseModel):
    """A single search result from a memory provider."""
    content: str
    score: float = 0.0
    source: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


# --- Evaluation models ---

class JudgeVerdict(BaseModel):
    """Result of a single answer evaluation."""
    question_id: str
    correct: bool
    explanation: str = ""


class QuestionResult(BaseModel):
    """Complete result for a single question through the pipeline."""
    question_id: str
    question: str
    question_type: str
    category: QuestionCategory
    expected_answer: str
    retrieved_context: list[str] = Field(default_factory=list)
    generated_answer: str = ""
    judge_verdict: JudgeVerdict | None = None
    search_latency_ms: float = 0.0
    context_tokens: int = 0
    error: str | None = None


# --- Report models ---

class CategoryScore(BaseModel):
    """Accuracy score for a single category."""
    category: QuestionCategory
    accuracy: float  # 0.0 to 1.0
    total: int
    correct: int


class BenchmarkSummary(BaseModel):
    """Top-level summary of a benchmark run."""
    run_id: str
    benchmark: str
    judge_model: str
    neocortex_git_sha: str
    dataset_version: str
    dataset_sha256: str
    timestamp: datetime
    total_questions: int
    overall_accuracy: float
    category_scores: list[CategoryScore]
    latency_p50_ms: float
    latency_p95_ms: float
    latency_p99_ms: float
    avg_context_tokens: float
    total_duration_seconds: float
    limit: int | None = None  # If run on subset


# --- Pipeline phase models ---

class PipelinePhase(str, Enum):
    """The 7 checkpointed pipeline phases."""
    SETUP = "setup"
    INGEST = "ingest"
    INDEX = "index"
    QUERY = "query"
    ANSWER = "answer"
    EVALUATE = "evaluate"
    REPORT = "report"


class PhaseResult(BaseModel):
    """Checkpoint data for a completed pipeline phase."""
    phase: PipelinePhase
    completed_at: datetime
    data: dict[str, Any] = Field(default_factory=dict)
```

#### 4. Entry point

**File**: `benchmarks/__main__.py`

```python
"""Entry point: python -m benchmarks delegates to the pipeline CLI."""

from benchmarks.runners.pipeline import main

if __name__ == "__main__":
    main()
```

#### 5. `benchmarks/__init__.py`

```python
"""NeoCortex benchmarking harness."""
```

All other `__init__.py` files are empty.

### Success Criteria

#### Automated Verification:
- [ ] `python -c "from benchmarks.models import BenchmarkQuestion, MemoryProvider; print('OK')"` — (MemoryProvider from Phase 1 base.py stub)
- [ ] All model classes instantiate with valid data
- [ ] `ruff check benchmarks/` passes
- [ ] Directory structure matches the tree above

#### Manual Verification:
- [ ] `.gitignore` excludes `benchmarks/datasets/*` and `benchmarks/reports/results/*`

---

## Phase 2: Dataset Downloader

### Overview

Implement `download_datasets.py` to fetch LongMemEval from HuggingFace with SHA256 integrity verification and version pinning.

### Changes Required

#### 1. Dataset downloader

**File**: `benchmarks/download_datasets.py`

```python
"""Download and verify benchmark datasets.

Usage:
    uv run python benchmarks/download_datasets.py [--force]
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import httpx

DATASETS_DIR = Path(__file__).parent / "datasets"

# Version-pinned dataset definitions
DATASETS: dict[str, dict] = {
    "longmemeval": {
        "url": "https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned/resolve/main/longmemeval_s_cleaned.json",
        "filename": "longmemeval_s_cleaned.json",
        "subdir": "longmemeval",
        "sha256": None,  # Set after first verified download
        "description": "LongMemEval-S: 500 questions, ~80 sessions each, ~115K tokens per instance",
    },
}


def compute_sha256(path: Path) -> str:
    """Compute SHA256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def download_dataset(name: str, force: bool = False) -> Path:
    """Download a single dataset, verify integrity, return path."""
    spec = DATASETS[name]
    dest_dir = DATASETS_DIR / spec["subdir"]
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file = dest_dir / spec["filename"]

    if dest_file.exists() and not force:
        print(f"  {name}: already exists at {dest_file}")
        if spec["sha256"]:
            actual = compute_sha256(dest_file)
            if actual != spec["sha256"]:
                print(f"  WARNING: SHA256 mismatch! Expected {spec['sha256']}, got {actual}")
                print(f"  Re-download with --force or update the expected hash.")
                sys.exit(1)
            print(f"  SHA256 verified: {actual[:16]}...")
        return dest_file

    print(f"  {name}: downloading from {spec['url']}...")
    with httpx.stream("GET", spec["url"], follow_redirects=True, timeout=300) as r:
        r.raise_for_status()
        with open(dest_file, "wb") as f:
            for chunk in r.iter_bytes(chunk_size=8192):
                f.write(chunk)

    actual_sha = compute_sha256(dest_file)
    print(f"  Downloaded: {dest_file} ({dest_file.stat().st_size / 1024 / 1024:.1f} MB)")
    print(f"  SHA256: {actual_sha}")

    if spec["sha256"] and actual_sha != spec["sha256"]:
        print(f"  ERROR: SHA256 mismatch! Expected {spec['sha256']}")
        dest_file.unlink()
        sys.exit(1)

    # Write manifest alongside the data file
    manifest = dest_dir / "manifest.json"
    manifest.write_text(json.dumps({
        "url": spec["url"],
        "sha256": actual_sha,
        "filename": spec["filename"],
        "size_bytes": dest_file.stat().st_size,
    }, indent=2))

    return dest_file


def main() -> None:
    force = "--force" in sys.argv
    print("Downloading benchmark datasets...")
    for name in DATASETS:
        download_dataset(name, force=force)
    print("Done.")


if __name__ == "__main__":
    main()
```

**Key design decisions:**
- Uses `httpx` (already a project dependency via fastmcp) for streaming download.
- SHA256 is `None` initially — set after first verified download. This follows WAYS_OF_WORKING §3: "Pin exact URLs and versions. Record SHA256 checksums."
- Writes a `manifest.json` next to each dataset for audit trail.
- `--force` flag re-downloads even if file exists.

### Success Criteria

#### Automated Verification:
- [ ] `uv run python benchmarks/download_datasets.py` downloads `longmemeval_s_cleaned.json` to `benchmarks/datasets/longmemeval/`
- [ ] `benchmarks/datasets/longmemeval/manifest.json` contains URL and SHA256
- [ ] Re-running without `--force` skips download
- [ ] `ruff check benchmarks/download_datasets.py` passes

#### Manual Verification:
- [ ] Downloaded JSON is valid and contains 500 records
- [ ] File is gitignored (not tracked)

**Implementation Note:** After first successful download, update `DATASETS["longmemeval"]["sha256"]` with the actual hash from `manifest.json`.

---

## Phase 3: MemoryProvider Protocol + NeoCortex Adapter

### Overview

Define the `MemoryProvider` protocol (matching MemoryBench's Provider interface shape) and implement the NeoCortex adapter with 3 configurable transport options: MCP, REST, and direct protocol.

### Changes Required

#### 1. MemoryProvider protocol

**File**: `benchmarks/adapters/base.py`

```python
"""Abstract MemoryProvider protocol for benchmark adapters."""

from __future__ import annotations

from typing import Protocol

from benchmarks.models import IngestResult, SearchResult, Session


class MemoryProvider(Protocol):
    """Interface that all benchmark adapters must satisfy.

    Matches MemoryBench's Provider interface shape so Track A/B
    stay interchangeable at the data level.
    """

    async def initialize(self) -> None:
        """Set up the provider (connect, authenticate, etc.)."""
        ...

    async def ingest_sessions(self, sessions: list[Session]) -> IngestResult:
        """Ingest conversation sessions into the memory system."""
        ...

    async def await_indexing(self, result: IngestResult) -> None:
        """Wait until ingested data is fully indexed and searchable."""
        ...

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        """Search memory for relevant results."""
        ...

    async def clear(self) -> None:
        """Clear all data from the provider (for clean benchmark runs)."""
        ...
```

#### 2. NeoCortex adapter

**File**: `benchmarks/adapters/neocortex_adapter.py`

```python
"""NeoCortex adapter implementing MemoryProvider.

Three transport modes:
- "direct": Uses MemoryRepository protocol directly (lowest overhead, for profiling)
- "mcp": Uses fastmcp.Client to call remember/recall tools (tests full MCP stack)
- "rest": Uses httpx to call ingestion REST API + MCP for recall (tests REST path)
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Literal

import httpx
from fastmcp import Client
from pydantic import BaseModel

from benchmarks.models import IngestResult, SearchResult, Session

if TYPE_CHECKING:
    from neocortex.db.protocol import MemoryRepository


class NeoCortexConfig(BaseModel):
    """Configuration for the NeoCortex adapter."""

    transport: Literal["direct", "mcp", "rest"] = "direct"

    # MCP transport settings
    mcp_url: str = "http://localhost:8000/mcp"

    # REST transport settings
    rest_url: str = "http://localhost:8001"

    # Direct transport settings (mock_db controls InMemory vs PG)
    mock_db: bool = False

    # Auth
    auth_token: str | None = None
    agent_id: str = "benchmark"


class NeoCortexAdapter:
    """MemoryProvider implementation targeting NeoCortex."""

    def __init__(self, config: NeoCortexConfig) -> None:
        self._config = config
        self._repo: MemoryRepository | None = None
        self._mcp_client: Client | None = None
        self._http_client: httpx.AsyncClient | None = None

    async def initialize(self) -> None:
        if self._config.transport == "direct":
            await self._init_direct()
        elif self._config.transport == "mcp":
            self._mcp_client = Client(self._config.mcp_url)
        elif self._config.transport == "rest":
            headers = {}
            if self._config.auth_token:
                headers["Authorization"] = f"Bearer {self._config.auth_token}"
            self._http_client = httpx.AsyncClient(
                base_url=self._config.rest_url,
                headers=headers,
                timeout=60.0,
            )

    async def _init_direct(self) -> None:
        """Initialize direct protocol access."""
        from neocortex.mcp_settings import MCPSettings
        from neocortex.services import create_services

        settings = MCPSettings(mock_db=self._config.mock_db, auth_mode="none")
        ctx = await create_services(settings)
        self._repo = ctx["repo"]

    async def ingest_sessions(self, sessions: list[Session]) -> IngestResult:
        """Ingest sessions via the configured transport."""
        if self._config.transport == "direct":
            return await self._ingest_direct(sessions)
        elif self._config.transport == "mcp":
            return await self._ingest_mcp(sessions)
        else:
            return await self._ingest_rest(sessions)

    async def _ingest_direct(self, sessions: list[Session]) -> IngestResult:
        assert self._repo is not None
        episode_ids: list[int] = []
        errors: list[str] = []
        for session in sessions:
            try:
                # Concatenate all messages in the session into one episode
                text = "\n".join(
                    f"{msg.role.value}: {msg.content}" for msg in session.messages
                )
                context = f"session:{session.session_id}"
                eid = await self._repo.store_episode(
                    agent_id=self._config.agent_id,
                    content=text,
                    context=context,
                    source_type="benchmark",
                )
                episode_ids.append(eid)
            except Exception as e:
                errors.append(f"Session {session.session_id}: {e}")
        return IngestResult(
            episode_ids=episode_ids,
            sessions_ingested=len(episode_ids),
            errors=errors,
        )

    async def _ingest_mcp(self, sessions: list[Session]) -> IngestResult:
        assert self._mcp_client is not None
        episode_ids: list[int] = []
        errors: list[str] = []
        async with self._mcp_client as client:
            for session in sessions:
                try:
                    text = "\n".join(
                        f"{msg.role.value}: {msg.content}" for msg in session.messages
                    )
                    result = await client.call_tool(
                        "remember",
                        {"text": text, "context": f"session:{session.session_id}"},
                    )
                    if result.structured_content:
                        episode_ids.append(result.structured_content["episode_id"])
                except Exception as e:
                    errors.append(f"Session {session.session_id}: {e}")
        return IngestResult(
            episode_ids=episode_ids,
            sessions_ingested=len(episode_ids),
            errors=errors,
        )

    async def _ingest_rest(self, sessions: list[Session]) -> IngestResult:
        assert self._http_client is not None
        episode_ids: list[int] = []
        errors: list[str] = []
        for session in sessions:
            try:
                text = "\n".join(
                    f"{msg.role.value}: {msg.content}" for msg in session.messages
                )
                resp = await self._http_client.post(
                    "/ingest/text",
                    json={"text": text, "metadata": {"session_id": session.session_id}},
                )
                resp.raise_for_status()
                data = resp.json()
                episode_ids.append(data.get("episode_id", 0))
            except Exception as e:
                errors.append(f"Session {session.session_id}: {e}")
        return IngestResult(
            episode_ids=episode_ids,
            sessions_ingested=len(episode_ids),
            errors=errors,
        )

    async def await_indexing(self, result: IngestResult) -> None:
        """NeoCortex indexes synchronously on ingest, so this is a no-op.

        If embedding computation becomes async in the future, poll here.
        """
        await asyncio.sleep(0)  # Yield control, but no actual waiting needed

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        if self._config.transport == "direct":
            return await self._search_direct(query, limit)
        elif self._config.transport == "mcp":
            return await self._search_mcp(query, limit)
        else:
            # REST transport uses MCP for recall (no REST recall endpoint)
            return await self._search_mcp(query, limit)

    async def _search_direct(self, query: str, limit: int) -> list[SearchResult]:
        assert self._repo is not None
        items = await self._repo.recall(query, self._config.agent_id, limit)
        return [
            SearchResult(
                content=item.content,
                score=item.score,
                source=item.source or "",
                metadata={"source_kind": item.source_kind, "graph_name": item.graph_name},
            )
            for item in items
        ]

    async def _search_mcp(self, query: str, limit: int) -> list[SearchResult]:
        assert self._mcp_client is not None
        async with self._mcp_client as client:
            result = await client.call_tool("recall", {"query": query, "limit": limit})
            if not result.structured_content:
                return []
            return [
                SearchResult(
                    content=r["content"],
                    score=r.get("score", 0.0),
                    source=r.get("source", ""),
                )
                for r in result.structured_content.get("results", [])
            ]

    async def clear(self) -> None:
        """Clear benchmark data.

        For direct transport: reset the InMemoryRepository or drop schemas.
        For MCP/REST: would need a dedicated admin endpoint (not yet implemented).
        """
        if self._config.transport == "direct" and self._repo is not None:
            # For InMemoryRepository, create a fresh instance
            from neocortex.db.mock import InMemoryRepository

            if isinstance(self._repo, InMemoryRepository):
                self._repo = InMemoryRepository()
```

### Success Criteria

#### Automated Verification:
- [ ] `python -c "from benchmarks.adapters.base import MemoryProvider; print('OK')"` imports cleanly
- [ ] `python -c "from benchmarks.adapters.neocortex_adapter import NeoCortexAdapter, NeoCortexConfig; print('OK')"` imports cleanly
- [ ] `NeoCortexAdapter` satisfies `MemoryProvider` protocol (structural typing)
- [ ] `ruff check benchmarks/adapters/` passes

#### Manual Verification:
- [ ] Direct transport with `mock_db=True` can ingest a session and recall it
- [ ] Config model validates transport options correctly

**Implementation Note:** The MCP transport opens/closes the client connection per batch (ingest) and per search call. For production benchmarks this is fine — connection overhead is negligible compared to LLM judge costs.

---

## Phase 4: LongMemEval Loader

### Overview

Parse the LongMemEval dataset into `BenchmarkQuestion` and `Session` objects, mapping the 6 raw question types to 5 ability categories. Handle the mixed `answer` type (string/int/list in the raw data).

### Changes Required

#### 1. LongMemEval loader

**File**: `benchmarks/benchmarks/longmemeval.py`

```python
"""LongMemEval benchmark loader.

Parses the longmemeval_s_cleaned.json dataset into BenchmarkQuestion
and Session objects. Maps 6 raw question_type values to 5 ability categories.

Dataset: https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned
Paper: https://arxiv.org/abs/2410.10813 (ICLR 2025)
"""

from __future__ import annotations

import json
from pathlib import Path

from benchmarks.models import (
    BenchmarkQuestion,
    MessageRole,
    QuestionCategory,
    Session,
    SessionMessage,
)

DATASET_PATH = Path(__file__).parent.parent / "datasets" / "longmemeval" / "longmemeval_s_cleaned.json"

# Map raw question_type → QuestionCategory
QUESTION_TYPE_TO_CATEGORY: dict[str, QuestionCategory] = {
    "single-session-user": QuestionCategory.INFORMATION_EXTRACTION,
    "single-session-assistant": QuestionCategory.INFORMATION_EXTRACTION,
    "single-session-preference": QuestionCategory.INFORMATION_EXTRACTION,
    "multi-session": QuestionCategory.MULTI_SESSION_REASONING,
    "temporal-reasoning": QuestionCategory.TEMPORAL_REASONING,
    "knowledge-update": QuestionCategory.KNOWLEDGE_UPDATES,
}


def _normalize_answer(answer: str | int | list) -> str:
    """Normalize the mixed-type answer field to a string."""
    if isinstance(answer, list):
        return "; ".join(str(a) for a in answer)
    return str(answer)


def _parse_datetime(date_str: str) -> str | None:
    """Parse LongMemEval date format 'YYYY/MM/DD HH:MM' or return None."""
    if not date_str or not date_str.strip():
        return None
    return date_str.strip()


def load_questions(
    path: Path | None = None,
    limit: int | None = None,
) -> list[BenchmarkQuestion]:
    """Load and parse LongMemEval questions.

    Args:
        path: Override dataset path (default: standard location).
        limit: Maximum number of questions to load (for dev iteration).

    Returns:
        List of parsed BenchmarkQuestion objects.
    """
    data_path = path or DATASET_PATH
    if not data_path.exists():
        raise FileNotFoundError(
            f"Dataset not found at {data_path}. "
            "Run: uv run python benchmarks/download_datasets.py"
        )

    raw = json.loads(data_path.read_text())

    questions: list[BenchmarkQuestion] = []
    for record in raw:
        qid = record["question_id"]

        # Abstention is identified by _abs suffix, regardless of question_type
        is_abstention = qid.endswith("_abs")
        raw_type = record["question_type"]

        if is_abstention:
            category = QuestionCategory.ABSTENTION
        else:
            category = QUESTION_TYPE_TO_CATEGORY.get(raw_type)
            if category is None:
                raise ValueError(f"Unknown question_type '{raw_type}' for question {qid}")

        questions.append(
            BenchmarkQuestion(
                question_id=qid,
                question=record["question"],
                question_type=raw_type,
                category=category,
                expected_answer=_normalize_answer(record["answer"]),
                question_date=record.get("question_date"),
                answer_session_ids=record.get("answer_session_ids", []),
                metadata={
                    "haystack_session_ids": record.get("haystack_session_ids", []),
                },
            )
        )

        if limit and len(questions) >= limit:
            break

    return questions


def load_sessions_for_question(
    question_id: str,
    path: Path | None = None,
) -> list[Session]:
    """Load the haystack sessions for a specific question.

    Each question in LongMemEval has its own set of ~80 sessions
    (the "haystack" through which the system must search).

    Returns:
        List of Session objects with parsed messages.
    """
    data_path = path or DATASET_PATH
    raw = json.loads(data_path.read_text())

    # Find the record for this question
    record = None
    for r in raw:
        if r["question_id"] == question_id:
            record = r
            break

    if record is None:
        raise ValueError(f"Question {question_id} not found in dataset")

    sessions: list[Session] = []
    haystack_dates = record.get("haystack_dates", [])
    haystack_session_ids = record.get("haystack_session_ids", [])

    for i, raw_session in enumerate(record["haystack_sessions"]):
        session_id = (
            haystack_session_ids[i]
            if i < len(haystack_session_ids)
            else f"{question_id}-session-{i}"
        )

        messages = [
            SessionMessage(
                role=MessageRole(turn["role"]),
                content=turn["content"],
                has_answer=turn.get("has_answer", False),
            )
            for turn in raw_session
        ]

        timestamp = None
        if i < len(haystack_dates):
            ts_str = _parse_datetime(haystack_dates[i])
            if ts_str:
                # Store as string in metadata; Session.timestamp expects datetime
                pass

        sessions.append(
            Session(
                session_id=session_id,
                messages=messages,
                timestamp=None,  # Timestamps stored as metadata if needed
            )
        )

    return sessions


def get_category_distribution(questions: list[BenchmarkQuestion]) -> dict[str, int]:
    """Return count of questions per category."""
    dist: dict[str, int] = {}
    for q in questions:
        key = q.category.value
        dist[key] = dist.get(key, 0) + 1
    return dist
```

**Key design decisions:**
- `load_questions()` loads all 500 questions at once (metadata only, no sessions — those are loaded per-question during the pipeline's INGEST phase).
- `load_sessions_for_question()` loads sessions for a single question. This avoids loading all 500 × 80 sessions into memory simultaneously.
- Mixed `answer` type handled by `_normalize_answer()` — converts int/list to string.
- Abstention detection via `_abs` suffix on `question_id` (not `question_type`), per the LongMemEval dataset convention.

### Success Criteria

#### Automated Verification:
- [ ] After downloading dataset: `python -c "from benchmarks.benchmarks.longmemeval import load_questions; qs = load_questions(); print(len(qs))"` prints `500`
- [ ] `get_category_distribution()` returns counts for all 5 categories
- [ ] `load_questions(limit=10)` returns exactly 10 questions
- [ ] `load_sessions_for_question(qs[0].question_id)` returns ~80 sessions
- [ ] `ruff check benchmarks/benchmarks/` passes

#### Manual Verification:
- [ ] All 5 categories are represented in the loaded questions
- [ ] Abstention questions are correctly identified (expect ~30)

---

## Phase 5: LLM Judge + F1 Scorer

### Overview

Implement the GPT-4o LLM judge matching LongMemEval's `evaluate_qa.py` methodology (5 question-type-specific prompts, binary yes/no scoring) and a token-level F1 scorer for cross-reference.

### Changes Required

#### 1. LLM judge

**File**: `benchmarks/judges/llm_judge.py`

```python
"""LLM-as-judge evaluator matching LongMemEval's evaluate_qa.py methodology.

Uses 5 question-type-specific prompts with binary yes/no scoring.
Supports GPT-4o (default), Claude, and a mock judge for testing.

Reference: https://github.com/xiaowu0162/LongMemEval/blob/main/src/evaluation/evaluate_qa.py
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from benchmarks.models import JudgeVerdict, QuestionCategory

# --- Prompt templates (matching LongMemEval evaluate_qa.py exactly) ---

_BASE_PROMPT = """\
I will give you a question, a correct answer, and a response from a model. \
Please answer yes if the response contains the correct answer. Otherwise, \
answer no. If the response is equivalent to the correct answer or contains \
all the intermediate steps to get the correct answer, you should also answer \
yes. If the response only contains a subset of the information required by \
the answer, answer no.

Question: {question}

Correct Answer: {answer}

Model Response: {hypothesis}

Is the model response correct? Answer yes or no only."""

_TEMPORAL_ADDENDUM = """
In addition, do not penalize off-by-one errors for the number of days. \
If the question asks for the number of days/weeks/months, etc., and the model \
makes off-by-one errors (e.g., predicting 19 days when the answer is 18), the \
model's response is still correct."""

_KNOWLEDGE_UPDATE_ADDENDUM = """
If the response contains some previous information along with an updated \
answer, the response should be considered as correct as long as the updated \
answer is the required answer."""

_PREFERENCE_ADDENDUM = """
The model does not need to reflect all the points in the rubric. The response \
is correct as long as it recalls and utilizes the user's personal information \
correctly."""

_ABSTENTION_PROMPT = """\
I will give you a question, a correct answer, and a response from a model. \
The correct answer indicates this question is unanswerable based on the \
conversation history.

Question: {question}

Correct Answer: {answer}

Model Response: {hypothesis}

Does the model correctly identify the question as unanswerable? Answer yes or no only."""


def _get_judge_prompt(
    question: str,
    answer: str,
    hypothesis: str,
    category: QuestionCategory,
    question_type: str,
) -> str:
    """Build the judge prompt for a given question type."""
    if category == QuestionCategory.ABSTENTION:
        return _ABSTENTION_PROMPT.format(
            question=question, answer=answer, hypothesis=hypothesis
        )

    base = _BASE_PROMPT.format(
        question=question, answer=answer, hypothesis=hypothesis
    )

    if category == QuestionCategory.TEMPORAL_REASONING:
        return base + _TEMPORAL_ADDENDUM
    elif category == QuestionCategory.KNOWLEDGE_UPDATES:
        return base + _KNOWLEDGE_UPDATE_ADDENDUM
    elif question_type == "single-session-preference":
        return base + _PREFERENCE_ADDENDUM
    else:
        return base


class JudgeConfig(BaseModel):
    """Configuration for the LLM judge."""

    model: Literal["gpt-4o", "gpt-4o-mini", "claude-sonnet", "mock"] = "gpt-4o"
    temperature: float = 0.0
    max_tokens: int = 10


class LLMJudge:
    """LLM-as-judge following LongMemEval's evaluation methodology."""

    def __init__(self, config: JudgeConfig) -> None:
        self._config = config
        self._client = None

    async def initialize(self) -> None:
        """Set up the LLM client."""
        if self._config.model == "mock":
            return

        if self._config.model.startswith("gpt"):
            import openai

            self._client = openai.AsyncOpenAI()
        elif self._config.model.startswith("claude"):
            import anthropic

            self._client = anthropic.AsyncAnthropic()

    async def evaluate(
        self,
        question: str,
        expected_answer: str,
        generated_answer: str,
        category: QuestionCategory,
        question_type: str,
    ) -> JudgeVerdict:
        """Evaluate a single answer against ground truth."""
        if self._config.model == "mock":
            return self._mock_evaluate(question, expected_answer, generated_answer)

        prompt = _get_judge_prompt(
            question=question,
            answer=expected_answer,
            hypothesis=generated_answer,
            category=category,
            question_type=question_type,
        )

        response_text = await self._call_llm(prompt)
        correct = "yes" in response_text.lower()

        return JudgeVerdict(
            question_id="",  # Caller sets this
            correct=correct,
            explanation=response_text.strip(),
        )

    async def _call_llm(self, prompt: str) -> str:
        """Call the configured LLM."""
        if self._config.model.startswith("gpt"):
            import openai

            assert isinstance(self._client, openai.AsyncOpenAI)
            resp = await self._client.chat.completions.create(
                model=self._config.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self._config.temperature,
                max_tokens=self._config.max_tokens,
            )
            return resp.choices[0].message.content or ""
        elif self._config.model.startswith("claude"):
            import anthropic

            assert isinstance(self._client, anthropic.AsyncAnthropic)
            resp = await self._client.messages.create(
                model="claude-sonnet-4-20250514",
                messages=[{"role": "user", "content": prompt}],
                temperature=self._config.temperature,
                max_tokens=self._config.max_tokens,
            )
            return resp.content[0].text if resp.content else ""

        return ""

    def _mock_evaluate(
        self,
        question: str,
        expected_answer: str,
        generated_answer: str,
    ) -> JudgeVerdict:
        """Mock judge: exact substring match (for smoke tests only)."""
        correct = expected_answer.lower() in generated_answer.lower()
        return JudgeVerdict(
            question_id="",
            correct=correct,
            explanation=f"Mock judge: {'match' if correct else 'no match'}",
        )
```

#### 2. F1 scorer

**File**: `benchmarks/judges/f1_judge.py`

```python
"""Token-level F1 scorer for cross-reference with LLM judge results.

This implements the standard token-level F1 metric used in the original
LoCoMo paper and provides a secondary signal alongside the LLM judge.
"""

from __future__ import annotations

import re
import string


def _normalize(text: str) -> str:
    """Lowercase, remove punctuation and extra whitespace."""
    text = text.lower()
    text = text.translate(str.maketrans("", "", string.punctuation))
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _tokenize(text: str) -> list[str]:
    """Split normalized text into tokens."""
    return _normalize(text).split()


def compute_f1(prediction: str, reference: str) -> float:
    """Compute token-level F1 between prediction and reference.

    Returns:
        F1 score in [0.0, 1.0].
    """
    pred_tokens = _tokenize(prediction)
    ref_tokens = _tokenize(reference)

    if not pred_tokens and not ref_tokens:
        return 1.0
    if not pred_tokens or not ref_tokens:
        return 0.0

    common = set(pred_tokens) & set(ref_tokens)
    if not common:
        return 0.0

    precision = len(common) / len(pred_tokens)
    recall = len(common) / len(ref_tokens)
    return 2 * precision * recall / (precision + recall)
```

### Success Criteria

#### Automated Verification:
- [ ] `compute_f1("The cat sat", "The cat sat on the mat")` returns a valid float in (0, 1]
- [ ] `compute_f1("completely wrong", "the right answer")` returns a low score
- [ ] Mock judge returns consistent results: `_mock_evaluate("q", "tea", "I like oolong tea")` returns `correct=True`
- [ ] `_get_judge_prompt()` produces different prompts for each category
- [ ] `ruff check benchmarks/judges/` passes

#### Manual Verification:
- [ ] GPT-4o judge prompt matches LongMemEval's `evaluate_qa.py` exactly (compare side-by-side)

---

## Phase 6: Checkpoint System + Pipeline Orchestrator

### Overview

Build the core pipeline: a 7-phase orchestrator (setup → ingest → index → query → answer → evaluate → report) with phase-level checkpointing for resume-on-failure. This is the central piece that wires together the adapter, loader, judge, and reporter.

### Changes Required

#### 1. Checkpoint system

**File**: `benchmarks/runners/checkpoint.py`

```python
"""Phase-level checkpointing for benchmark pipeline runs.

Each phase writes its output to:
  benchmarks/reports/results/{run_id}/{phase}.json

On resume, the pipeline skips completed phases and starts from the
first incomplete one.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from benchmarks.models import PhaseResult, PipelinePhase

RESULTS_DIR = Path(__file__).parent.parent / "reports" / "results"


def get_run_dir(run_id: str) -> Path:
    """Return the directory for a specific run, creating if needed."""
    d = RESULTS_DIR / run_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_checkpoint(run_id: str, phase: PipelinePhase, data: dict) -> None:
    """Save checkpoint data for a completed phase."""
    run_dir = get_run_dir(run_id)
    result = PhaseResult(
        phase=phase,
        completed_at=datetime.now(timezone.utc),
        data=data,
    )
    checkpoint_file = run_dir / f"{phase.value}.json"
    checkpoint_file.write_text(result.model_dump_json(indent=2))


def load_checkpoint(run_id: str, phase: PipelinePhase) -> PhaseResult | None:
    """Load checkpoint data for a phase, or None if not completed."""
    run_dir = RESULTS_DIR / run_id
    checkpoint_file = run_dir / f"{phase.value}.json"
    if not checkpoint_file.exists():
        return None
    raw = json.loads(checkpoint_file.read_text())
    return PhaseResult(**raw)


def get_resume_phase(run_id: str) -> PipelinePhase:
    """Determine which phase to resume from.

    Returns the first phase that has no checkpoint.
    """
    for phase in PipelinePhase:
        if load_checkpoint(run_id, phase) is None:
            return phase
    # All phases complete
    return PipelinePhase.REPORT
```

#### 2. Pipeline orchestrator

**File**: `benchmarks/runners/pipeline.py`

```python
"""Benchmark pipeline orchestrator.

Runs the 7-phase pipeline:
  SETUP → INGEST → INDEX → QUERY → ANSWER → EVALUATE → REPORT

Usage:
    uv run python -m benchmarks.runners.pipeline \\
        --benchmark longmemeval \\
        --judge gpt-4o \\
        --run-id my-run \\
        --limit 50

    # Resume a failed run:
    uv run python -m benchmarks.runners.pipeline \\
        --benchmark longmemeval \\
        --judge gpt-4o \\
        --run-id my-run \\
        --resume
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from benchmarks.adapters.neocortex_adapter import NeoCortexAdapter, NeoCortexConfig
from benchmarks.judges.f1_judge import compute_f1
from benchmarks.judges.llm_judge import JudgeConfig, LLMJudge
from benchmarks.models import (
    BenchmarkQuestion,
    BenchmarkSummary,
    CategoryScore,
    PipelinePhase,
    QuestionCategory,
    QuestionResult,
    SearchResult,
    Session,
)
from benchmarks.reports.generator import generate_report
from benchmarks.runners.checkpoint import (
    get_resume_phase,
    get_run_dir,
    load_checkpoint,
    save_checkpoint,
)


def _get_git_sha() -> str:
    """Get the current git SHA."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()[:12]
    except Exception:
        return "unknown"


def _build_answer_prompt(question: str, context: list[str]) -> str:
    """Build the QA prompt for the answering LLM.

    The model receives the retrieved context and must answer the question
    based solely on that context.
    """
    context_text = "\n\n---\n\n".join(context) if context else "(no context retrieved)"
    return f"""\
Based on the following conversation history, answer the question concisely.
If the information is not available in the context, say "I don't know" or
"This was not mentioned."

Context:
{context_text}

Question: {question}

Answer:"""


class BenchmarkPipeline:
    """Orchestrates the 7-phase benchmark pipeline."""

    def __init__(
        self,
        benchmark: str,
        judge_model: str,
        run_id: str,
        limit: int | None = None,
        resume: bool = False,
        transport: str = "direct",
        mock_db: bool = False,
    ) -> None:
        self.benchmark = benchmark
        self.judge_model = judge_model
        self.run_id = run_id
        self.limit = limit
        self.resume = resume
        self.transport = transport
        self.mock_db = mock_db

        self._adapter: NeoCortexAdapter | None = None
        self._judge: LLMJudge | None = None
        self._questions: list[BenchmarkQuestion] = []
        self._results: list[QuestionResult] = []

    async def run(self) -> BenchmarkSummary:
        """Execute the full pipeline, respecting checkpoints."""
        start_time = time.time()
        run_dir = get_run_dir(self.run_id)

        start_phase = (
            get_resume_phase(self.run_id) if self.resume else PipelinePhase.SETUP
        )
        print(f"Pipeline starting from phase: {start_phase.value}")

        phases = list(PipelinePhase)
        start_idx = phases.index(start_phase)

        for phase in phases[start_idx:]:
            print(f"\n{'='*60}")
            print(f"Phase: {phase.value.upper()}")
            print(f"{'='*60}")

            if phase == PipelinePhase.SETUP:
                await self._phase_setup()
            elif phase == PipelinePhase.INGEST:
                await self._phase_ingest()
            elif phase == PipelinePhase.INDEX:
                await self._phase_index()
            elif phase == PipelinePhase.QUERY:
                await self._phase_query()
            elif phase == PipelinePhase.ANSWER:
                await self._phase_answer()
            elif phase == PipelinePhase.EVALUATE:
                await self._phase_evaluate()
            elif phase == PipelinePhase.REPORT:
                summary = await self._phase_report(
                    total_duration=time.time() - start_time,
                )
                return summary

        raise RuntimeError("Pipeline did not complete report phase")

    async def _phase_setup(self) -> None:
        """SETUP: Initialize adapter, judge, and load questions."""
        # Initialize adapter
        config = NeoCortexConfig(
            transport=self.transport,  # type: ignore[arg-type]
            mock_db=self.mock_db,
        )
        self._adapter = NeoCortexAdapter(config)
        await self._adapter.initialize()

        # Initialize judge
        judge_config = JudgeConfig(model=self.judge_model)  # type: ignore[arg-type]
        self._judge = LLMJudge(judge_config)
        await self._judge.initialize()

        # Load questions
        if self.benchmark == "longmemeval":
            from benchmarks.benchmarks.longmemeval import load_questions

            self._questions = load_questions(limit=self.limit)
        else:
            raise ValueError(f"Unknown benchmark: {self.benchmark}")

        # Clear previous data
        await self._adapter.clear()

        save_checkpoint(self.run_id, PipelinePhase.SETUP, {
            "benchmark": self.benchmark,
            "judge_model": self.judge_model,
            "transport": self.transport,
            "mock_db": self.mock_db,
            "total_questions": len(self._questions),
            "limit": self.limit,
        })
        print(f"  Loaded {len(self._questions)} questions")

    async def _phase_ingest(self) -> None:
        """INGEST: Load sessions for each question and ingest into NeoCortex."""
        assert self._adapter is not None

        if self.benchmark == "longmemeval":
            from benchmarks.benchmarks.longmemeval import load_sessions_for_question

            # Each question has its own haystack sessions
            total_sessions = 0
            for i, q in enumerate(self._questions):
                sessions = load_sessions_for_question(q.question_id)
                result = await self._adapter.ingest_sessions(sessions)
                total_sessions += result.sessions_ingested
                if (i + 1) % 10 == 0 or i == 0:
                    print(f"  Ingested {i + 1}/{len(self._questions)} questions ({total_sessions} sessions)")

            save_checkpoint(self.run_id, PipelinePhase.INGEST, {
                "total_sessions": total_sessions,
                "total_questions": len(self._questions),
            })
            print(f"  Total sessions ingested: {total_sessions}")

    async def _phase_index(self) -> None:
        """INDEX: Wait for indexing to complete."""
        assert self._adapter is not None

        from benchmarks.models import IngestResult

        await self._adapter.await_indexing(IngestResult())
        save_checkpoint(self.run_id, PipelinePhase.INDEX, {"status": "complete"})
        print("  Indexing complete (synchronous)")

    async def _phase_query(self) -> None:
        """QUERY: For each question, search NeoCortex for relevant context."""
        assert self._adapter is not None

        self._results = []
        for i, q in enumerate(self._questions):
            start = time.time()
            try:
                results: list[SearchResult] = await self._adapter.search(q.question, limit=10)
                latency_ms = (time.time() - start) * 1000
                self._results.append(
                    QuestionResult(
                        question_id=q.question_id,
                        question=q.question,
                        question_type=q.question_type,
                        category=q.category,
                        expected_answer=q.expected_answer,
                        retrieved_context=[r.content for r in results],
                        search_latency_ms=latency_ms,
                    )
                )
            except Exception as e:
                self._results.append(
                    QuestionResult(
                        question_id=q.question_id,
                        question=q.question,
                        question_type=q.question_type,
                        category=q.category,
                        expected_answer=q.expected_answer,
                        error=str(e),
                    )
                )

            if (i + 1) % 50 == 0 or i == 0:
                print(f"  Queried {i + 1}/{len(self._questions)}")

        # Save query results as checkpoint
        save_checkpoint(self.run_id, PipelinePhase.QUERY, {
            "results": [r.model_dump() for r in self._results],
        })
        print(f"  Queried all {len(self._questions)} questions")

    async def _phase_answer(self) -> None:
        """ANSWER: Generate answers from retrieved context using an LLM."""
        # Load from checkpoint if resuming
        if not self._results:
            cp = load_checkpoint(self.run_id, PipelinePhase.QUERY)
            if cp:
                self._results = [QuestionResult(**r) for r in cp.data["results"]]

        for i, result in enumerate(self._results):
            if result.error:
                result.generated_answer = f"Error: {result.error}"
                continue

            # For mock judge runs, generate a simple answer from context
            if self.judge_model == "mock":
                result.generated_answer = " ".join(result.retrieved_context[:3])
                # Count approximate tokens
                result.context_tokens = sum(
                    len(c.split()) for c in result.retrieved_context
                )
            else:
                # Use the same LLM as the judge to generate answers
                prompt = _build_answer_prompt(result.question, result.retrieved_context)
                assert self._judge is not None
                # For real runs, use OpenAI/Anthropic to generate the answer
                result.generated_answer = await self._generate_answer(prompt)
                result.context_tokens = sum(
                    len(c.split()) for c in result.retrieved_context
                )

            if (i + 1) % 50 == 0 or i == 0:
                print(f"  Answered {i + 1}/{len(self._results)}")

        save_checkpoint(self.run_id, PipelinePhase.ANSWER, {
            "results": [r.model_dump() for r in self._results],
        })
        print(f"  Generated {len(self._results)} answers")

    async def _generate_answer(self, prompt: str) -> str:
        """Generate an answer using the configured LLM."""
        try:
            import openai

            client = openai.AsyncOpenAI()
            resp = await client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=256,
            )
            return resp.choices[0].message.content or ""
        except Exception as e:
            return f"Generation error: {e}"

    async def _phase_evaluate(self) -> None:
        """EVALUATE: Score each answer using the LLM judge and F1."""
        assert self._judge is not None

        # Load from checkpoint if resuming
        if not self._results:
            cp = load_checkpoint(self.run_id, PipelinePhase.ANSWER)
            if cp:
                self._results = [QuestionResult(**r) for r in cp.data["results"]]

        for i, result in enumerate(self._results):
            # LLM judge
            verdict = await self._judge.evaluate(
                question=result.question,
                expected_answer=result.expected_answer,
                generated_answer=result.generated_answer,
                category=result.category,
                question_type=result.question_type,
            )
            verdict.question_id = result.question_id
            result.judge_verdict = verdict

            if (i + 1) % 50 == 0 or i == 0:
                print(f"  Evaluated {i + 1}/{len(self._results)}")

        save_checkpoint(self.run_id, PipelinePhase.EVALUATE, {
            "results": [r.model_dump() for r in self._results],
        })

        correct = sum(1 for r in self._results if r.judge_verdict and r.judge_verdict.correct)
        print(f"  Overall: {correct}/{len(self._results)} correct ({100*correct/max(len(self._results),1):.1f}%)")

    async def _phase_report(self, total_duration: float) -> BenchmarkSummary:
        """REPORT: Generate summary.json, report.md, and failures.jsonl."""
        # Load from checkpoint if resuming
        if not self._results:
            cp = load_checkpoint(self.run_id, PipelinePhase.EVALUATE)
            if cp:
                self._results = [QuestionResult(**r) for r in cp.data["results"]]

        # Load questions for metadata
        if not self._questions:
            cp_setup = load_checkpoint(self.run_id, PipelinePhase.SETUP)
            if cp_setup:
                self.benchmark = cp_setup.data.get("benchmark", self.benchmark)

        # Compute per-category scores
        category_scores = self._compute_category_scores()

        # Compute latency stats
        latencies = [r.search_latency_ms for r in self._results if r.search_latency_ms > 0]
        latencies.sort()

        def percentile(data: list[float], p: float) -> float:
            if not data:
                return 0.0
            idx = int(len(data) * p / 100)
            return data[min(idx, len(data) - 1)]

        # Load dataset manifest for SHA
        manifest_path = Path(__file__).parent.parent / "datasets" / "longmemeval" / "manifest.json"
        dataset_sha = ""
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text())
            dataset_sha = manifest.get("sha256", "")

        overall_correct = sum(1 for r in self._results if r.judge_verdict and r.judge_verdict.correct)
        summary = BenchmarkSummary(
            run_id=self.run_id,
            benchmark=self.benchmark,
            judge_model=self.judge_model,
            neocortex_git_sha=_get_git_sha(),
            dataset_version="longmemeval_s_cleaned",
            dataset_sha256=dataset_sha,
            timestamp=datetime.now(timezone.utc),
            total_questions=len(self._results),
            overall_accuracy=overall_correct / max(len(self._results), 1),
            category_scores=category_scores,
            latency_p50_ms=percentile(latencies, 50),
            latency_p95_ms=percentile(latencies, 95),
            latency_p99_ms=percentile(latencies, 99),
            avg_context_tokens=(
                sum(r.context_tokens for r in self._results) / max(len(self._results), 1)
            ),
            total_duration_seconds=total_duration,
            limit=self.limit,
        )

        # Generate reports
        run_dir = get_run_dir(self.run_id)
        generate_report(summary, self._results, run_dir)

        save_checkpoint(self.run_id, PipelinePhase.REPORT, {
            "summary": summary.model_dump(),
        })

        print(f"\n  Reports written to: {run_dir}")
        print(f"  Overall accuracy: {summary.overall_accuracy:.1%}")
        return summary

    def _compute_category_scores(self) -> list[CategoryScore]:
        """Compute accuracy per QuestionCategory."""
        from collections import defaultdict

        buckets: dict[QuestionCategory, list[bool]] = defaultdict(list)
        for r in self._results:
            if r.judge_verdict:
                buckets[r.category].append(r.judge_verdict.correct)

        scores = []
        for cat in QuestionCategory:
            verdicts = buckets.get(cat, [])
            correct = sum(verdicts)
            total = len(verdicts)
            scores.append(
                CategoryScore(
                    category=cat,
                    accuracy=correct / max(total, 1),
                    total=total,
                    correct=correct,
                )
            )
        return scores


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="NeoCortex Benchmark Pipeline")
    parser.add_argument("--benchmark", required=True, choices=["longmemeval"])
    parser.add_argument("--judge", required=True, choices=["gpt-4o", "gpt-4o-mini", "claude-sonnet", "mock"])
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--limit", type=int, default=None, help="Limit questions for dev iteration")
    parser.add_argument("--resume", action="store_true", help="Resume from last checkpoint")
    parser.add_argument("--transport", default="direct", choices=["direct", "mcp", "rest"])
    parser.add_argument("--mock-db", action="store_true", help="Use InMemoryRepository (smoke tests only)")
    args = parser.parse_args()

    pipeline = BenchmarkPipeline(
        benchmark=args.benchmark,
        judge_model=args.judge,
        run_id=args.run_id,
        limit=args.limit,
        resume=args.resume,
        transport=args.transport,
        mock_db=args.mock_db,
    )

    summary = asyncio.run(pipeline.run())
    print(f"\nDone. Overall accuracy: {summary.overall_accuracy:.1%}")


if __name__ == "__main__":
    main()
```

### Success Criteria

#### Automated Verification:
- [ ] `python -m benchmarks.runners.pipeline --help` shows usage
- [ ] Checkpoint files are written to `benchmarks/reports/results/{run_id}/` as JSON
- [ ] `get_resume_phase()` correctly identifies the first incomplete phase
- [ ] Pipeline phases execute in order: setup → ingest → index → query → answer → evaluate → report
- [ ] `ruff check benchmarks/runners/` passes

#### Manual Verification:
- [ ] `--resume` flag skips completed phases
- [ ] Checkpoint JSON files are human-readable and contain expected data

**Implementation Note:** After completing this phase and all automated verification passes, pause for manual confirmation before proceeding to Phase 7.

---

## Phase 7: Report Generator

### Overview

Generate the three output files: `summary.json` (machine-readable), `report.md` (human-readable with tables), and `failures.jsonl` (diagnostic tool for every incorrect answer).

### Changes Required

#### 1. Report generator

**File**: `benchmarks/reports/generator.py`

```python
"""Report generator for benchmark runs.

Produces three output files per run:
- summary.json: Machine-readable metrics
- report.md: Human-readable report with tables and failure examples
- failures.jsonl: Every incorrect answer with full diagnostic context
"""

from __future__ import annotations

import json
from pathlib import Path

from benchmarks.judges.f1_judge import compute_f1
from benchmarks.models import BenchmarkSummary, QuestionResult


def generate_report(
    summary: BenchmarkSummary,
    results: list[QuestionResult],
    output_dir: Path,
) -> None:
    """Generate all report files."""
    output_dir.mkdir(parents=True, exist_ok=True)

    _write_summary_json(summary, output_dir)
    _write_failures_jsonl(results, output_dir)
    _write_report_md(summary, results, output_dir)


def _write_summary_json(summary: BenchmarkSummary, output_dir: Path) -> None:
    path = output_dir / "summary.json"
    path.write_text(summary.model_dump_json(indent=2))


def _write_failures_jsonl(results: list[QuestionResult], output_dir: Path) -> None:
    """Write every incorrect answer with full diagnostic context.

    Per WAYS_OF_WORKING §5: preserve failure evidence.
    """
    path = output_dir / "failures.jsonl"
    with open(path, "w") as f:
        for r in results:
            if r.judge_verdict and not r.judge_verdict.correct:
                record = {
                    "question_id": r.question_id,
                    "question": r.question,
                    "question_type": r.question_type,
                    "category": r.category.value,
                    "expected_answer": r.expected_answer,
                    "generated_answer": r.generated_answer,
                    "retrieved_context": r.retrieved_context,
                    "judge_explanation": r.judge_verdict.explanation,
                    "f1_score": compute_f1(r.generated_answer, r.expected_answer),
                    "search_latency_ms": r.search_latency_ms,
                    "context_tokens": r.context_tokens,
                }
                f.write(json.dumps(record) + "\n")


def _write_report_md(
    summary: BenchmarkSummary,
    results: list[QuestionResult],
    output_dir: Path,
) -> None:
    """Write human-readable Markdown report."""
    lines: list[str] = []

    # Header
    lines.append(f"# Benchmark Report: {summary.benchmark}")
    lines.append("")
    lines.append(f"**Run ID:** {summary.run_id}")
    lines.append(f"**Timestamp:** {summary.timestamp.isoformat()}")
    lines.append(f"**NeoCortex SHA:** {summary.neocortex_git_sha}")
    lines.append(f"**Judge:** {summary.judge_model}")
    lines.append(f"**Dataset:** {summary.dataset_version}")
    if summary.limit:
        lines.append(f"**Limit:** {summary.limit} questions (subset)")
    lines.append("")

    # Overall
    lines.append("## Overall Results")
    lines.append("")
    lines.append(f"- **Accuracy:** {summary.overall_accuracy:.1%} ({int(summary.overall_accuracy * summary.total_questions)}/{summary.total_questions})")
    lines.append(f"- **Latency:** p50={summary.latency_p50_ms:.0f}ms, p95={summary.latency_p95_ms:.0f}ms, p99={summary.latency_p99_ms:.0f}ms")
    lines.append(f"- **Avg context tokens:** {summary.avg_context_tokens:.0f}")
    lines.append(f"- **Duration:** {summary.total_duration_seconds:.0f}s")
    lines.append("")

    # Per-category table
    lines.append("## Per-Category Accuracy")
    lines.append("")
    lines.append("| Category | Accuracy | Correct | Total |")
    lines.append("|----------|----------|---------|-------|")
    for cs in summary.category_scores:
        lines.append(f"| {cs.category.value} | {cs.accuracy:.1%} | {cs.correct} | {cs.total} |")
    lines.append("")

    # Competitor comparison
    lines.append("## Competitor Reference")
    lines.append("")
    lines.append("| System | LongMemEval |")
    lines.append("|--------|-------------|")
    lines.append(f"| **NeoCortex** | **{summary.overall_accuracy:.1%}** |")
    lines.append("| Supermemory | 81.6% |")
    lines.append("| Zep/Graphiti | 71.2% |")
    lines.append("")

    # Failure examples (first 5)
    failures = [r for r in results if r.judge_verdict and not r.judge_verdict.correct]
    if failures:
        lines.append(f"## Failure Examples ({len(failures)} total, showing first 5)")
        lines.append("")
        for r in failures[:5]:
            lines.append(f"### {r.question_id} ({r.question_type})")
            lines.append(f"**Q:** {r.question}")
            lines.append(f"**Expected:** {r.expected_answer}")
            lines.append(f"**Got:** {r.generated_answer[:200]}")
            if r.judge_verdict:
                lines.append(f"**Judge:** {r.judge_verdict.explanation}")
            lines.append("")

    lines.append("---")
    lines.append(f"*Generated by NeoCortex benchmarking harness. Dataset SHA256: {summary.dataset_sha256[:16]}...*")

    path = output_dir / "report.md"
    path.write_text("\n".join(lines))
```

### Success Criteria

#### Automated Verification:
- [ ] `generate_report()` creates all three files: `summary.json`, `report.md`, `failures.jsonl`
- [ ] `summary.json` is valid JSON matching `BenchmarkSummary` schema
- [ ] `failures.jsonl` has one JSON object per line
- [ ] `report.md` contains per-category accuracy table
- [ ] `ruff check benchmarks/reports/` passes

#### Manual Verification:
- [ ] `report.md` is readable and includes competitor reference scores
- [ ] `failures.jsonl` includes all required diagnostic fields per WAYS_OF_WORKING §5

---

## Phase 8: Docker Compose Extension

### Overview

Create `docker-compose.bench.yml` that extends the main `docker-compose.yml` with an isolated benchmark database, preventing benchmark runs from polluting the development database.

### Changes Required

#### 1. Docker compose extension

**File**: `benchmarks/docker-compose.bench.yml`

```yaml
# Docker Compose extension for benchmark runs.
# Usage: docker compose -f docker-compose.yml -f benchmarks/docker-compose.bench.yml up -d
#
# This extends the main compose file to provide an isolated PostgreSQL
# instance for benchmarking. The benchmark DB uses a separate volume
# so benchmark runs don't pollute the development database.

services:
  postgres-bench:
    image: pgvector/pgvector:0.8.0-pg16
    ports:
      - "5433:5432"  # Different port to avoid conflict with dev DB
    environment:
      POSTGRES_USER: neocortex
      POSTGRES_PASSWORD: neocortex
      POSTGRES_DB: neocortex_bench
    volumes:
      - pgdata-bench:/var/lib/postgresql/data
      - ../migrations/init:/docker-entrypoint-initdb.d:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U neocortex -d neocortex_bench"]
      interval: 5s
      timeout: 5s
      retries: 10

volumes:
  pgdata-bench:
```

**Note:** When running benchmarks against the isolated DB, set environment variables:
```bash
export POSTGRES_PORT=5433
export POSTGRES_DB=neocortex_bench
```

### Success Criteria

#### Automated Verification:
- [ ] `docker compose -f docker-compose.yml -f benchmarks/docker-compose.bench.yml config` validates without errors
- [ ] `docker compose -f docker-compose.yml -f benchmarks/docker-compose.bench.yml up -d postgres-bench` starts the benchmark DB on port 5433

#### Manual Verification:
- [ ] Dev DB (port 5432) and benchmark DB (port 5433) can run simultaneously
- [ ] Migrations apply to the benchmark DB on first start

---

## Phase 9: Smoke Test

### Overview

End-to-end test: run the full pipeline with mock DB and mock judge on 5 questions. This validates the complete wiring without Docker or LLM API costs.

### Changes Required

#### 1. Smoke test

**File**: `benchmarks/conftest.py`

```python
"""Shared pytest fixtures for benchmark tests."""

from __future__ import annotations

import pytest


@pytest.fixture
def sample_dataset_path(tmp_path):
    """Create a minimal LongMemEval-format dataset for testing."""
    import json

    records = [
        {
            "question_id": f"test_q{i}",
            "question_type": "single-session-user",
            "question": f"What is the user's favorite color #{i}?",
            "answer": f"blue_{i}",
            "question_date": "2025/01/01 10:00",
            "haystack_session_ids": [f"s{i}_0", f"s{i}_1"],
            "haystack_dates": ["2024/12/01 10:00", "2024/12/15 10:00"],
            "haystack_sessions": [
                [
                    {"role": "user", "content": f"My favorite color is blue_{i}.", "has_answer": True},
                    {"role": "assistant", "content": "That's a nice color!"},
                ],
                [
                    {"role": "user", "content": "Let's talk about something else."},
                    {"role": "assistant", "content": "Sure, what would you like to discuss?"},
                ],
            ],
            "answer_session_ids": [f"s{i}_0"],
        }
        for i in range(5)
    ]

    # Add one abstention question
    records.append({
        "question_id": "test_q5_abs",
        "question_type": "single-session-user",
        "question": "What is the user's favorite movie?",
        "answer": "This was not mentioned in the conversation.",
        "question_date": "2025/01/01 10:00",
        "haystack_session_ids": ["s5_0"],
        "haystack_dates": ["2024/12/01 10:00"],
        "haystack_sessions": [
            [
                {"role": "user", "content": "I like hiking."},
                {"role": "assistant", "content": "Hiking is great!"},
            ],
        ],
        "answer_session_ids": [],
    })

    dataset_file = tmp_path / "longmemeval" / "longmemeval_s_cleaned.json"
    dataset_file.parent.mkdir(parents=True, exist_ok=True)
    dataset_file.write_text(json.dumps(records))
    return dataset_file
```

**File**: `benchmarks/tests/__init__.py` — empty

**File**: `benchmarks/tests/test_smoke.py`

```python
"""Smoke test: full pipeline with mock DB + mock judge.

Validates the complete wiring end-to-end without Docker or LLM costs.
"""

from __future__ import annotations

import pytest

from benchmarks.benchmarks.longmemeval import (
    get_category_distribution,
    load_questions,
    load_sessions_for_question,
)
from benchmarks.judges.f1_judge import compute_f1
from benchmarks.judges.llm_judge import JudgeConfig, LLMJudge
from benchmarks.models import QuestionCategory


# --- Loader tests ---


def test_load_questions(sample_dataset_path):
    questions = load_questions(path=sample_dataset_path)
    assert len(questions) == 6  # 5 normal + 1 abstention


def test_load_questions_with_limit(sample_dataset_path):
    questions = load_questions(path=sample_dataset_path, limit=3)
    assert len(questions) == 3


def test_abstention_detection(sample_dataset_path):
    questions = load_questions(path=sample_dataset_path)
    abstention = [q for q in questions if q.category == QuestionCategory.ABSTENTION]
    assert len(abstention) == 1
    assert abstention[0].question_id == "test_q5_abs"


def test_category_distribution(sample_dataset_path):
    questions = load_questions(path=sample_dataset_path)
    dist = get_category_distribution(questions)
    assert dist["information_extraction"] == 5
    assert dist["abstention"] == 1


def test_load_sessions(sample_dataset_path):
    sessions = load_sessions_for_question("test_q0", path=sample_dataset_path)
    assert len(sessions) == 2
    assert sessions[0].messages[0].role.value == "user"
    assert "blue_0" in sessions[0].messages[0].content


# --- F1 scorer tests ---


def test_f1_exact_match():
    assert compute_f1("the answer is blue", "the answer is blue") == 1.0


def test_f1_partial_match():
    score = compute_f1("blue", "the answer is blue")
    assert 0.0 < score < 1.0


def test_f1_no_match():
    score = compute_f1("completely wrong", "the answer is blue")
    # "the" might overlap but score should be very low
    assert score < 0.5


def test_f1_empty():
    assert compute_f1("", "") == 1.0
    assert compute_f1("something", "") == 0.0
    assert compute_f1("", "something") == 0.0


# --- Mock judge tests ---


@pytest.mark.asyncio
async def test_mock_judge_correct():
    judge = LLMJudge(JudgeConfig(model="mock"))
    await judge.initialize()
    verdict = await judge.evaluate(
        question="What color?",
        expected_answer="blue",
        generated_answer="The user's favorite color is blue.",
        category=QuestionCategory.INFORMATION_EXTRACTION,
        question_type="single-session-user",
    )
    assert verdict.correct is True


@pytest.mark.asyncio
async def test_mock_judge_incorrect():
    judge = LLMJudge(JudgeConfig(model="mock"))
    await judge.initialize()
    verdict = await judge.evaluate(
        question="What color?",
        expected_answer="blue",
        generated_answer="The user likes red.",
        category=QuestionCategory.INFORMATION_EXTRACTION,
        question_type="single-session-user",
    )
    assert verdict.correct is False


# --- Full pipeline smoke test ---


@pytest.mark.asyncio
async def test_pipeline_smoke(sample_dataset_path, tmp_path):
    """End-to-end smoke test with mock DB + mock judge."""
    import json

    from benchmarks.runners.pipeline import BenchmarkPipeline

    # Monkey-patch the dataset path
    import benchmarks.benchmarks.longmemeval as lme_module

    original_path = lme_module.DATASET_PATH
    lme_module.DATASET_PATH = sample_dataset_path

    try:
        pipeline = BenchmarkPipeline(
            benchmark="longmemeval",
            judge_model="mock",
            run_id="smoke-test",
            limit=3,
            transport="direct",
            mock_db=True,
        )

        summary = await pipeline.run()

        # Verify summary
        assert summary.benchmark == "longmemeval"
        assert summary.total_questions == 3
        assert 0.0 <= summary.overall_accuracy <= 1.0
        assert len(summary.category_scores) == len(QuestionCategory)

        # Verify output files
        from benchmarks.runners.checkpoint import get_run_dir

        run_dir = get_run_dir("smoke-test")
        assert (run_dir / "summary.json").exists()
        assert (run_dir / "report.md").exists()
        assert (run_dir / "failures.jsonl").exists()

        # Verify summary.json is valid
        summary_data = json.loads((run_dir / "summary.json").read_text())
        assert summary_data["benchmark"] == "longmemeval"
        assert "category_scores" in summary_data
    finally:
        lme_module.DATASET_PATH = original_path
```

### Success Criteria

#### Automated Verification:
- [ ] `uv run pytest benchmarks/tests/ -v` — all tests pass
- [ ] `test_pipeline_smoke` completes end-to-end without errors
- [ ] Pipeline produces `summary.json`, `report.md`, and `failures.jsonl`
- [ ] `ruff check benchmarks/` passes across all modules

#### Manual Verification:
- [ ] `NEOCORTEX_MOCK_DB=true uv run python -m benchmarks.runners.pipeline --benchmark longmemeval --judge mock --run-id smoke --limit 5` runs successfully from the command line
- [ ] Output `report.md` is readable and contains expected sections

**Implementation Note:** This is the exit criteria for Stage 1. After all automated tests pass, run the CLI smoke test manually to confirm the full integration.

---

## Testing Strategy

### Unit Tests (in `benchmarks/tests/`)
- Loader: question parsing, category mapping, abstention detection, limit
- F1 scorer: exact match, partial match, no match, empty strings
- Mock judge: correct/incorrect verdicts
- Checkpoint: save/load/resume logic
- Report generator: output format validation

### Integration Test
- `test_pipeline_smoke`: full end-to-end with mock DB + mock judge

### Manual Testing
1. Download real dataset: `uv run python benchmarks/download_datasets.py`
2. Run smoke: `NEOCORTEX_MOCK_DB=true uv run python -m benchmarks.runners.pipeline --benchmark longmemeval --judge mock --run-id manual-smoke --limit 5`
3. Verify `report.md` output
4. (After Stage 1) Run against real PG: `docker compose -f docker-compose.yml -f benchmarks/docker-compose.bench.yml up -d && uv run python -m benchmarks.runners.pipeline --benchmark longmemeval --judge gpt-4o --run-id first-real --limit 20`

---

## Dependencies to Add

The following packages need to be added to `pyproject.toml` optional dependencies (or a benchmark extras group):

```toml
[project.optional-dependencies]
benchmark = [
    "openai>=1.0",     # For GPT-4o judge
    "tiktoken>=0.7",   # For context token counting
]
```

`httpx` and `pydantic` are already project dependencies. `anthropic` is optional (only needed if using Claude judge).

---

## Performance Considerations

- **Memory:** Each LongMemEval question has ~80 sessions × ~1.4K tokens = ~115K tokens. Loading all 500 questions' sessions simultaneously would require ~57.5M tokens in memory. The pipeline loads sessions per-question during INGEST to avoid this.
- **LLM costs:** Full LongMemEval run with GPT-4o judge ≈ $5-15. Use `--limit N` for iteration. Mock judge costs $0.
- **Checkpoint overhead:** Each phase writes JSON to disk. This is negligible compared to LLM API latency and enables resume-on-failure (critical for runs hitting rate limits).

---

## Migration Notes

- No database migrations needed — benchmarking never modifies `src/neocortex/`.
- `.gitignore` must be updated to exclude datasets and results.
- `pyproject.toml` gets a `[project.optional-dependencies] benchmark` section.

---

## References

- Parent plan: `docs/plans/benchmarking/07-benchmarking-plan.md`
- Ways of working: `docs/plans/benchmarking/WAYS_OF_WORKING.md`
- LongMemEval paper: [ICLR 2025](https://arxiv.org/abs/2410.10813)
- LongMemEval dataset: [HuggingFace xiaowu0162/longmemeval-cleaned](https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned)
- LongMemEval eval script: [evaluate_qa.py](https://github.com/xiaowu0162/LongMemEval/blob/main/src/evaluation/evaluate_qa.py)
- MemoryBench Provider: [supermemoryai/memorybench](https://github.com/supermemoryai/memorybench)
- NeoCortex protocol: `src/neocortex/db/protocol.py`
- Test patterns: `tests/mcp/test_tools.py`, `tests/test_ingestion_api.py`
