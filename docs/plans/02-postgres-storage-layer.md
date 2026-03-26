# Plan: PostgreSQL Storage Layer for NeoCortex

## Overview

Set up the foundational storage layer for the NeoCortex agent memory system. This includes a Docker Compose environment with PostgreSQL 16 (pgvector + tsvector), pre-generated SQL migrations, and a Python SDK with two service layers: `PostgresService` (connection management, health checks, migrations) and `GraphService` (ontology CRUD, node/edge/episode CRUD, basic search). This layer is the foundation on which the MCP memory server will be built.

## Prerequisites

Before starting, ensure the following are available on your machine:

- **Docker** and **Docker Compose** installed and the Docker daemon running
- **uv** package manager (used instead of pip/poetry)
- **Python 3.13+** (see `.python-version`)
- **Port 5432** is free (no other PostgreSQL instance running)

Quick check: `docker compose version && uv --version && python3 --version`

## Execution Protocol

To execute this plan, follow this loop for each stage:

1. **Read the progress tracker** below and find the first stage that is not DONE
2. **Read the stage details** — understand the goal, dependencies, and steps
3. **Clarify ambiguities** — if anything is unclear or multiple approaches exist, ask the user before implementing. Do not guess.
4. **Implement** — execute the steps described in the stage
5. **Validate** — run the verification checks listed in the stage. If validation fails, fix the issue before proceeding. Do not skip verification.
6. **Update this plan** — mark the stage as DONE in the progress tracker, add brief notes about what was done and any deviations from the original steps
7. **Commit** — create an atomic commit with the message specified in the stage. Include all changed files (code, config, docs, and this plan file).

Repeat until all stages are DONE or a stage is BLOCKED.

**If a stage cannot be completed**: mark it BLOCKED in the tracker with a note explaining why, and stop. Do not proceed to subsequent stages.

**If assumptions are wrong**: stop, document the issue in the Issues section below, revise affected stages, and get user confirmation before continuing.

## Progress Tracker

| # | Stage | Status | Notes | Commit |
|---|-------|--------|-------|--------|
| 1 | Docker Compose + SQL Migrations | PENDING | | |
| 2 | Package Skeleton + PostgresService | PENDING | | |
| 3 | GraphService — Ontology & Data CRUD | PENDING | | |
| 4 | GraphService — Search Methods | PENDING | | |
| 5 | Integration Tests & Verification | PENDING | | |
| 6 | Push to Remote | PENDING | | |

Statuses: `PENDING` → `IN_PROGRESS` → `DONE` | `BLOCKED`

---

## Stage 1: Docker Compose + SQL Migrations

**Goal**: Runnable PostgreSQL 16 with pgvector and full-text search, with schema applied automatically on first start.
**Dependencies**: None

### Steps

#### 1.1 Create `docker-compose.yml` in project root

```yaml
services:
  postgres:
    image: pgvector/pgvector:0.8.0-pg16
    container_name: neocortex-postgres
    environment:
      POSTGRES_DB: neocortex
      POSTGRES_USER: neocortex
      POSTGRES_PASSWORD: neocortex
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./migrations/init:/docker-entrypoint-initdb.d
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U neocortex -d neocortex"]
      interval: 5s
      timeout: 3s
      retries: 5

volumes:
  pgdata:
    driver: local
```

Key points:
- `pgvector/pgvector:0.8.0-pg16` image has pgvector pre-installed (pinned for reproducibility)
- Named volume `pgdata` for local persistence across restarts
- `migrations/init/` mounted to `/docker-entrypoint-initdb.d` — PostgreSQL runs these `.sql` files alphabetically on first init only
- Health check ensures container reports healthy only when PG is accepting connections

#### 1.2 Create `migrations/init/001_extensions.sql`

```sql
-- Enable required PostgreSQL extensions
CREATE EXTENSION IF NOT EXISTS vector;       -- pgvector for embeddings
CREATE EXTENSION IF NOT EXISTS pg_trgm;      -- trigram index support for fuzzy text
```

Note: `tsvector` is built into PostgreSQL core — no extension needed. `pg_trgm` is useful for trigram similarity on names.

#### 1.3 Create `migrations/init/002_schema.sql`

Full schema based on `docs/plans/01-high-level-hackathon-plan.md`:

```sql
-- =============================================================
-- NeoCortex Graph Schema
-- =============================================================

-- Ontology: what types of nodes exist
CREATE TABLE node_type (
    id          SERIAL PRIMARY KEY,
    name        TEXT UNIQUE NOT NULL,
    description TEXT,
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- Ontology: what types of edges exist
CREATE TABLE edge_type (
    id          SERIAL PRIMARY KEY,
    name        TEXT UNIQUE NOT NULL,
    description TEXT,
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- Graph nodes (entities/memories)
CREATE TABLE node (
    id          SERIAL PRIMARY KEY,
    type_id     INT NOT NULL REFERENCES node_type(id),
    name        TEXT NOT NULL,
    content     TEXT,
    properties  JSONB DEFAULT '{}',
    embedding   vector(768),
    tsv         tsvector GENERATED ALWAYS AS (
                    to_tsvector('english', coalesce(name, '') || ' ' || coalesce(content, ''))
                ) STORED,
    source      TEXT,
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now()
);

-- Graph edges (relationships between nodes)
CREATE TABLE edge (
    id          SERIAL PRIMARY KEY,
    source_id   INT NOT NULL REFERENCES node(id) ON DELETE CASCADE,
    target_id   INT NOT NULL REFERENCES node(id) ON DELETE CASCADE,
    type_id     INT NOT NULL REFERENCES edge_type(id),
    weight      FLOAT DEFAULT 1.0,
    properties  JSONB DEFAULT '{}',
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- Episodic memory log (raw, append-only)
CREATE TABLE episode (
    id          SERIAL PRIMARY KEY,
    agent_id    TEXT NOT NULL,
    content     TEXT NOT NULL,
    embedding   vector(768),
    source_type TEXT,
    metadata    JSONB DEFAULT '{}',
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- Migration tracking (for application-level migrations beyond init)
CREATE TABLE _migration (
    id          SERIAL PRIMARY KEY,
    name        TEXT UNIQUE NOT NULL,
    applied_at  TIMESTAMPTZ DEFAULT now()
);
```

#### 1.4 Create `migrations/init/003_indexes.sql`

```sql
-- =============================================================
-- Indexes for search and traversal
-- =============================================================

-- Vector similarity search (cosine) on nodes — HNSW works on empty tables
CREATE INDEX idx_node_embedding ON node
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Full-text search (GIN) on auto-generated tsvector
CREATE INDEX idx_node_tsv ON node USING GIN (tsv);

-- Trigram index on node name for fuzzy matching
CREATE INDEX idx_node_name_trgm ON node USING GIN (name gin_trgm_ops);

-- Graph traversal indexes on edges
CREATE INDEX idx_edge_source ON edge (source_id);
CREATE INDEX idx_edge_target ON edge (target_id);
CREATE INDEX idx_edge_type ON edge (type_id);
CREATE INDEX idx_edge_source_type ON edge (source_id, type_id);

-- Episode lookup by agent + time
CREATE INDEX idx_episode_agent ON episode (agent_id, created_at DESC);

-- Vector similarity search on episodes — HNSW works on empty tables
CREATE INDEX idx_episode_embedding ON episode
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Ontology lookups by name
CREATE INDEX idx_node_type_name ON node_type (name);
CREATE INDEX idx_edge_type_name ON edge_type (name);

-- Node filtering by type
CREATE INDEX idx_node_type ON node (type_id);
```

**Note**: HNSW indexes are used instead of IVFFlat because they work correctly on empty tables (no training data needed) and perform well on small datasets. For very large datasets (millions of rows), consider switching to IVFFlat with appropriate `lists` parameter after initial data load.

#### 1.5 Create `migrations/init/004_seed_ontology.sql`

Seed default ontology types so the system is immediately usable:

```sql
-- =============================================================
-- Default ontology seed data
-- =============================================================

-- Default node types
INSERT INTO node_type (name, description) VALUES
    ('Concept',    'Abstract idea or topic'),
    ('Person',     'Human individual'),
    ('Document',   'Source document or file'),
    ('Event',      'Something that happened at a specific time'),
    ('Tool',       'Software tool, library, or technology'),
    ('Preference', 'User preference or opinion')
ON CONFLICT (name) DO NOTHING;

-- Default edge types
INSERT INTO edge_type (name, description) VALUES
    ('RELATES_TO',   'General relationship'),
    ('MENTIONS',     'Source mentions target'),
    ('CAUSED_BY',    'Target caused source'),
    ('FOLLOWS',      'Source follows target in sequence'),
    ('AUTHORED',     'Source authored target'),
    ('USES',         'Source uses target'),
    ('CONTRADICTS',  'Source contradicts target'),
    ('SUPPORTS',     'Source supports/confirms target'),
    ('SUMMARIZES',   'Source is a summary of target'),
    ('DERIVED_FROM', 'Source was derived from target')
ON CONFLICT (name) DO NOTHING;
```

#### 1.6 Create `.env.example` (committed) and `.env` (gitignored), update `.gitignore`

`.env.example` (committed to git — documents required env vars):
```
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=neocortex
POSTGRES_PASSWORD=neocortex
POSTGRES_DATABASE=neocortex
```

`.env` (gitignored — copy from `.env.example` and adjust if needed):
```
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=neocortex
POSTGRES_PASSWORD=neocortex
POSTGRES_DATABASE=neocortex
```

These env vars are loaded by `PostgresConfig` via pydantic-settings (prefix `POSTGRES_`). The defaults match the Docker Compose config, so `.env` is only needed if you change credentials.

Add to `.gitignore` (if not already present):
```
# Docker volumes (should not be committed)
pgdata/
```

Note: `.env` is already in the existing `.gitignore`.

### Verification

- [ ] `docker compose up -d` starts PostgreSQL container successfully
- [ ] `docker compose ps` shows `neocortex-postgres` as `healthy`
- [ ] `docker compose exec postgres psql -U neocortex -d neocortex -c "SELECT extname FROM pg_extension WHERE extname IN ('vector', 'pg_trgm');"` returns both extensions
- [ ] `docker compose exec postgres psql -U neocortex -d neocortex -c "\dt"` shows all 6 tables (node_type, edge_type, node, edge, episode, _migration)
- [ ] `docker compose exec postgres psql -U neocortex -d neocortex -c "SELECT count(*) FROM node_type;"` returns 6 (seed data)
- [ ] `docker compose down && docker compose up -d` — data persists (re-check seed count)

### Commit

`feat(storage): add Docker Compose with PostgreSQL 16 + pgvector and schema migrations`

---

## Stage 2: Package Skeleton + PostgresService

**Goal**: Python package `src/neocortex/` with `PostgresService` providing async connection pooling, health checks, and application-level migration support.
**Dependencies**: Stage 1

### Steps

#### 2.1 Update `pyproject.toml`

Add new dependencies to `[project] dependencies`:

```toml
dependencies = [
    "pydantic-ai-slim[google]>=1.72.0",
    "loguru>=0.7.3",
    "asyncpg>=0.30.0",
    "pydantic>=2.0",
    "pydantic-settings>=2.0",
]
```

Add pytest-asyncio to dev deps in `[dependency-groups]`:
```toml
[dependency-groups]
dev = [
    "ty",
    "ruff",
    "pre-commit",
    "black",
    "flake8",
    "pytest",
    "pytest-asyncio",
]
```

**Note**: No package discovery changes needed — `[tool.setuptools.packages.find] where = ["src"]` already auto-discovers any package under `src/` with an `__init__.py`. The `[tool.poetry]` section in `pyproject.toml` is vestigial (build system is setuptools); do not modify it.

#### 2.2 Create package structure

```
src/neocortex/
    __init__.py
    config.py
    postgres_service.py
```

#### 2.3 Implement `src/neocortex/__init__.py`

```python
"""NeoCortex - Agent Memory Storage Layer."""
```

#### 2.4 Implement `src/neocortex/config.py`

Settings loaded from environment variables or `.env`:

```python
from pydantic_settings import BaseSettings


class PostgresConfig(BaseSettings):
    """PostgreSQL connection configuration."""

    model_config = {"env_prefix": "POSTGRES_", "env_file": ".env", "env_file_encoding": "utf-8"}

    host: str = "localhost"
    port: int = 5432
    user: str = "neocortex"
    password: str = "neocortex"
    database: str = "neocortex"
    min_pool_size: int = 2
    max_pool_size: int = 10

    @property
    def dsn(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"
```

#### 2.5 Implement `src/neocortex/postgres_service.py`

Core class managing the asyncpg connection pool:

```python
import asyncpg
from loguru import logger
from neocortex.config import PostgresConfig


class PostgresService:
    """Manages PostgreSQL connections, health checks, and migrations."""

    def __init__(self, config: PostgresConfig | None = None):
        self._config = config or PostgresConfig()
        self._pool: asyncpg.Pool | None = None

    @property
    def pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("PostgresService not started. Call connect() first.")
        return self._pool

    async def connect(self) -> None:
        """Create connection pool."""
        logger.info("Connecting to PostgreSQL at {}:{}", self._config.host, self._config.port)
        self._pool = await asyncpg.create_pool(
            dsn=self._config.dsn,
            min_size=self._config.min_pool_size,
            max_size=self._config.max_pool_size,
        )
        logger.info("Connection pool created (min={}, max={})", self._config.min_pool_size, self._config.max_pool_size)

    async def disconnect(self) -> None:
        """Close connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None
            logger.info("Connection pool closed")

    async def health_check(self) -> dict:
        """Check database connectivity and return status info."""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT version() as version, current_database() as database, now() as server_time"
                )
                extensions = await conn.fetch(
                    "SELECT extname FROM pg_extension WHERE extname IN ('vector', 'pg_trgm') ORDER BY extname"
                )
                return {
                    "status": "healthy",
                    "version": row["version"],
                    "database": row["database"],
                    "server_time": str(row["server_time"]),
                    "extensions": [r["extname"] for r in extensions],
                    "pool_size": self.pool.get_size(),
                    "pool_free": self.pool.get_idle_size(),
                }
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}

    async def execute(self, query: str, *args) -> str:
        """Execute a query (INSERT, UPDATE, DELETE). Returns status string."""
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)

    async def fetch(self, query: str, *args) -> list[asyncpg.Record]:
        """Execute a query and return all rows."""
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def fetchrow(self, query: str, *args) -> asyncpg.Record | None:
        """Execute a query and return a single row."""
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def fetchval(self, query: str, *args) -> object:
        """Execute a query and return a single value."""
        async with self.pool.acquire() as conn:
            return await conn.fetchval(query, *args)

    async def apply_migration(self, name: str, sql: str) -> bool:
        """Apply a named migration if not already applied. Returns True if applied."""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                already = await conn.fetchval("SELECT 1 FROM _migration WHERE name = $1", name)
                if already:
                    logger.debug("Migration '{}' already applied, skipping", name)
                    return False
                await conn.execute(sql)
                await conn.execute("INSERT INTO _migration (name) VALUES ($1)", name)
                logger.info("Applied migration '{}'", name)
                return True

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()
```

### Verification

- [ ] `uv sync` installs new dependencies (asyncpg, pydantic-settings, pytest-asyncio) without errors
- [ ] `uv run python -c "from neocortex.postgres_service import PostgresService; print('import OK')"` succeeds
- [ ] `uv run python -c "from neocortex.config import PostgresConfig; c = PostgresConfig(); print(c.dsn)"` prints `postgresql://neocortex:neocortex@localhost:5432/neocortex`
- [ ] `uv run ruff check src/neocortex/` passes with no errors
- [ ] `uv run black --check src/neocortex/` passes

### Commit

`feat(neocortex): add package skeleton and PostgresService with connection pooling`

---

## Stage 3: GraphService — Ontology & Data CRUD

**Goal**: `GraphService` class providing typed CRUD operations for all graph entities: `node_type`, `edge_type`, `node`, `edge`, `episode`.
**Dependencies**: Stage 2

### Steps

#### 3.1 Create Pydantic models in `src/neocortex/models.py`

Data models representing graph entities, used as return types and input schemas:

```python
from datetime import datetime
from pydantic import BaseModel


class NodeType(BaseModel):
    id: int
    name: str
    description: str | None = None
    created_at: datetime


class EdgeType(BaseModel):
    id: int
    name: str
    description: str | None = None
    created_at: datetime


class Node(BaseModel):
    id: int
    type_id: int
    name: str
    content: str | None = None
    properties: dict = {}
    embedding: list[float] | None = None
    source: str | None = None
    created_at: datetime
    updated_at: datetime


class Edge(BaseModel):
    id: int
    source_id: int
    target_id: int
    type_id: int
    weight: float = 1.0
    properties: dict = {}
    created_at: datetime


class Episode(BaseModel):
    id: int
    agent_id: str
    content: str
    embedding: list[float] | None = None
    source_type: str | None = None
    metadata: dict = {}
    created_at: datetime
```

#### 3.2 Create `src/neocortex/graph_service.py`

```python
import json
from loguru import logger
from neocortex.models import Node, NodeType, Edge, EdgeType, Episode
from neocortex.postgres_service import PostgresService


class GraphService:
    """Graph layer for ontology manipulation and data CRUD on the NeoCortex knowledge graph."""

    def __init__(self, pg: PostgresService):
        self._pg = pg

    # ── Ontology: Node Types ─────────────────────────────────────

    async def create_node_type(self, name: str, description: str | None = None) -> NodeType:
        row = await self._pg.fetchrow(
            "INSERT INTO node_type (name, description) VALUES ($1, $2) RETURNING *",
            name, description,
        )
        return NodeType(**dict(row))

    async def get_node_type(self, id: int) -> NodeType | None:
        row = await self._pg.fetchrow("SELECT * FROM node_type WHERE id = $1", id)
        return NodeType(**dict(row)) if row else None

    async def get_node_type_by_name(self, name: str) -> NodeType | None:
        row = await self._pg.fetchrow("SELECT * FROM node_type WHERE name = $1", name)
        return NodeType(**dict(row)) if row else None

    async def list_node_types(self) -> list[NodeType]:
        rows = await self._pg.fetch("SELECT * FROM node_type ORDER BY name")
        return [NodeType(**dict(r)) for r in rows]

    async def update_node_type(self, id: int, name: str | None = None, description: str | None = None) -> NodeType | None:
        current = await self.get_node_type(id)
        if not current:
            return None
        row = await self._pg.fetchrow(
            "UPDATE node_type SET name = $1, description = $2 WHERE id = $3 RETURNING *",
            name if name is not None else current.name,
            description if description is not None else current.description,
            id,
        )
        return NodeType(**dict(row))

    async def delete_node_type(self, id: int) -> bool:
        result = await self._pg.execute("DELETE FROM node_type WHERE id = $1", id)
        return result == "DELETE 1"

    # ── Ontology: Edge Types ─────────────────────────────────────

    async def create_edge_type(self, name: str, description: str | None = None) -> EdgeType:
        row = await self._pg.fetchrow(
            "INSERT INTO edge_type (name, description) VALUES ($1, $2) RETURNING *",
            name, description,
        )
        return EdgeType(**dict(row))

    async def get_edge_type(self, id: int) -> EdgeType | None:
        row = await self._pg.fetchrow("SELECT * FROM edge_type WHERE id = $1", id)
        return EdgeType(**dict(row)) if row else None

    async def get_edge_type_by_name(self, name: str) -> EdgeType | None:
        row = await self._pg.fetchrow("SELECT * FROM edge_type WHERE name = $1", name)
        return EdgeType(**dict(row)) if row else None

    async def list_edge_types(self) -> list[EdgeType]:
        rows = await self._pg.fetch("SELECT * FROM edge_type ORDER BY name")
        return [EdgeType(**dict(r)) for r in rows]

    async def update_edge_type(self, id: int, name: str | None = None, description: str | None = None) -> EdgeType | None:
        current = await self.get_edge_type(id)
        if not current:
            return None
        row = await self._pg.fetchrow(
            "UPDATE edge_type SET name = $1, description = $2 WHERE id = $3 RETURNING *",
            name if name is not None else current.name,
            description if description is not None else current.description,
            id,
        )
        return EdgeType(**dict(row))

    async def delete_edge_type(self, id: int) -> bool:
        result = await self._pg.execute("DELETE FROM edge_type WHERE id = $1", id)
        return result == "DELETE 1"

    # ── Nodes ────────────────────────────────────────────────────

    async def create_node(
        self,
        type_id: int,
        name: str,
        content: str | None = None,
        properties: dict | None = None,
        embedding: list[float] | None = None,
        source: str | None = None,
    ) -> Node:
        # asyncpg needs JSON as string for JSONB columns
        props_json = json.dumps(properties or {})
        # pgvector accepts Python list or string representation
        emb_str = str(embedding) if embedding else None
        row = await self._pg.fetchrow(
            """INSERT INTO node (type_id, name, content, properties, embedding, source)
               VALUES ($1, $2, $3, $4::jsonb, $5::vector, $6)
               RETURNING id, type_id, name, content, properties, source, created_at, updated_at""",
            type_id, name, content, props_json, emb_str, source,
        )
        return self._row_to_node(row)

    async def get_node(self, id: int) -> Node | None:
        row = await self._pg.fetchrow(
            "SELECT id, type_id, name, content, properties, source, created_at, updated_at FROM node WHERE id = $1",
            id,
        )
        return self._row_to_node(row) if row else None

    async def list_nodes(self, type_id: int | None = None, limit: int = 100, offset: int = 0) -> list[Node]:
        if type_id is not None:
            rows = await self._pg.fetch(
                """SELECT id, type_id, name, content, properties, source, created_at, updated_at
                   FROM node WHERE type_id = $1 ORDER BY created_at DESC LIMIT $2 OFFSET $3""",
                type_id, limit, offset,
            )
        else:
            rows = await self._pg.fetch(
                """SELECT id, type_id, name, content, properties, source, created_at, updated_at
                   FROM node ORDER BY created_at DESC LIMIT $1 OFFSET $2""",
                limit, offset,
            )
        return [self._row_to_node(r) for r in rows]

    async def update_node(
        self,
        id: int,
        name: str | None = None,
        content: str | None = None,
        properties: dict | None = None,
        embedding: list[float] | None = None,
    ) -> Node | None:
        current = await self.get_node(id)
        if not current:
            return None
        props_json = json.dumps(properties) if properties is not None else json.dumps(current.properties)
        emb_str = str(embedding) if embedding is not None else None
        row = await self._pg.fetchrow(
            """UPDATE node SET
                name = $1, content = $2, properties = $3::jsonb,
                embedding = COALESCE($4::vector, embedding),
                updated_at = now()
               WHERE id = $5
               RETURNING id, type_id, name, content, properties, source, created_at, updated_at""",
            name if name is not None else current.name,
            content if content is not None else current.content,
            props_json,
            emb_str,
            id,
        )
        return self._row_to_node(row)

    async def delete_node(self, id: int) -> bool:
        result = await self._pg.execute("DELETE FROM node WHERE id = $1", id)
        return result == "DELETE 1"

    # ── Edges ────────────────────────────────────────────────────

    async def create_edge(
        self,
        source_id: int,
        target_id: int,
        type_id: int,
        weight: float = 1.0,
        properties: dict | None = None,
    ) -> Edge:
        props_json = json.dumps(properties or {})
        row = await self._pg.fetchrow(
            """INSERT INTO edge (source_id, target_id, type_id, weight, properties)
               VALUES ($1, $2, $3, $4, $5::jsonb)
               RETURNING *""",
            source_id, target_id, type_id, weight, props_json,
        )
        return self._row_to_edge(row)

    async def get_edge(self, id: int) -> Edge | None:
        row = await self._pg.fetchrow("SELECT * FROM edge WHERE id = $1", id)
        return self._row_to_edge(row) if row else None

    async def get_edges_from(self, source_id: int, type_id: int | None = None) -> list[Edge]:
        if type_id is not None:
            rows = await self._pg.fetch(
                "SELECT * FROM edge WHERE source_id = $1 AND type_id = $2 ORDER BY weight DESC",
                source_id, type_id,
            )
        else:
            rows = await self._pg.fetch(
                "SELECT * FROM edge WHERE source_id = $1 ORDER BY weight DESC", source_id,
            )
        return [self._row_to_edge(r) for r in rows]

    async def get_edges_to(self, target_id: int, type_id: int | None = None) -> list[Edge]:
        if type_id is not None:
            rows = await self._pg.fetch(
                "SELECT * FROM edge WHERE target_id = $1 AND type_id = $2 ORDER BY weight DESC",
                target_id, type_id,
            )
        else:
            rows = await self._pg.fetch(
                "SELECT * FROM edge WHERE target_id = $1 ORDER BY weight DESC", target_id,
            )
        return [self._row_to_edge(r) for r in rows]

    async def delete_edge(self, id: int) -> bool:
        result = await self._pg.execute("DELETE FROM edge WHERE id = $1", id)
        return result == "DELETE 1"

    # ── Episodes ─────────────────────────────────────────────────

    async def create_episode(
        self,
        agent_id: str,
        content: str,
        embedding: list[float] | None = None,
        source_type: str | None = None,
        metadata: dict | None = None,
    ) -> Episode:
        meta_json = json.dumps(metadata or {})
        emb_str = str(embedding) if embedding else None
        row = await self._pg.fetchrow(
            """INSERT INTO episode (agent_id, content, embedding, source_type, metadata)
               VALUES ($1, $2, $3::vector, $4, $5::jsonb)
               RETURNING id, agent_id, content, source_type, metadata, created_at""",
            agent_id, content, emb_str, source_type, meta_json,
        )
        return self._row_to_episode(row)

    async def get_episode(self, id: int) -> Episode | None:
        row = await self._pg.fetchrow(
            "SELECT id, agent_id, content, source_type, metadata, created_at FROM episode WHERE id = $1", id,
        )
        return self._row_to_episode(row) if row else None

    async def list_episodes(self, agent_id: str | None = None, limit: int = 50) -> list[Episode]:
        if agent_id:
            rows = await self._pg.fetch(
                """SELECT id, agent_id, content, source_type, metadata, created_at
                   FROM episode WHERE agent_id = $1 ORDER BY created_at DESC LIMIT $2""",
                agent_id, limit,
            )
        else:
            rows = await self._pg.fetch(
                """SELECT id, agent_id, content, source_type, metadata, created_at
                   FROM episode ORDER BY created_at DESC LIMIT $1""",
                limit,
            )
        return [self._row_to_episode(r) for r in rows]

    async def delete_episode(self, id: int) -> bool:
        result = await self._pg.execute("DELETE FROM episode WHERE id = $1", id)
        return result == "DELETE 1"

    # ── Neighbors (graph traversal helper) ───────────────────────

    async def get_neighbors(self, node_id: int) -> list[dict]:
        """Get immediate neighboring nodes (1-hop). Returns list of dicts with node info and edge metadata."""
        rows = await self._pg.fetch(
            """SELECT
                n.id, n.name, n.type_id, n.content, n.source, n.created_at,
                e.id as edge_id, e.type_id as edge_type_id, e.weight,
                et.name as edge_type_name,
                'outgoing' as direction
               FROM edge e
               JOIN node n ON n.id = e.target_id
               JOIN edge_type et ON et.id = e.type_id
               WHERE e.source_id = $1
             UNION ALL
             SELECT
                n.id, n.name, n.type_id, n.content, n.source, n.created_at,
                e.id as edge_id, e.type_id as edge_type_id, e.weight,
                et.name as edge_type_name,
                'incoming' as direction
               FROM edge e
               JOIN node n ON n.id = e.source_id
               JOIN edge_type et ON et.id = e.type_id
               WHERE e.target_id = $1
             ORDER BY weight DESC""",
            node_id,
        )
        return [dict(r) for r in rows]

    # ── Private helpers ──────────────────────────────────────────

    @staticmethod
    def _row_to_node(row) -> Node:
        d = dict(row)
        if isinstance(d.get("properties"), str):
            d["properties"] = json.loads(d["properties"])
        return Node(**d)

    @staticmethod
    def _row_to_edge(row) -> Edge:
        d = dict(row)
        if isinstance(d.get("properties"), str):
            d["properties"] = json.loads(d["properties"])
        return Edge(**d)

    @staticmethod
    def _row_to_episode(row) -> Episode:
        d = dict(row)
        if isinstance(d.get("metadata"), str):
            d["metadata"] = json.loads(d["metadata"])
        return Episode(**d)
```

### Verification

- [ ] `uv run ruff check src/neocortex/` passes
- [ ] `uv run black --check src/neocortex/` passes
- [ ] `uv run python -c "from neocortex.graph_service import GraphService; print('import OK')"` succeeds
- [ ] Manual smoke test: start Docker (`docker compose up -d`), create a temporary script, run it, verify output, then delete it before committing. The script should create a node_type, node, edge_type, edge, and episode, then read them back:

```python
# /tmp/smoke_graph.py (temporary — run then delete, do NOT commit)
import asyncio
from neocortex.postgres_service import PostgresService
from neocortex.graph_service import GraphService

async def main():
    async with PostgresService() as pg:
        gs = GraphService(pg)
        # List seed ontology
        types = await gs.list_node_types()
        print(f"Node types: {[t.name for t in types]}")
        # Create a node
        concept = await gs.get_node_type_by_name("Concept")
        node = await gs.create_node(type_id=concept.id, name="PostgreSQL", content="A relational database")
        print(f"Created node: {node}")
        # Create episode
        ep = await gs.create_episode(agent_id="test", content="Testing the graph service")
        print(f"Created episode: {ep}")

asyncio.run(main())
```

Run with `uv run python /tmp/smoke_graph.py`. Expected: node types list includes seed data, node and episode created successfully. Delete the script after verification.

### Commit

`feat(neocortex): add GraphService with ontology and data CRUD operations`

---

## Stage 4: GraphService — Search Methods

**Goal**: Add basic search capabilities to `GraphService`: vector similarity search, full-text BM25 search, and a combined method.
**Dependencies**: Stage 3

### Steps

#### 4.1 Add search methods to `src/neocortex/graph_service.py`

Append these methods to the `GraphService` class:

```python
    # ── Search: Vector Similarity ────────────────────────────────

    async def search_by_vector(self, embedding: list[float], limit: int = 10, type_id: int | None = None) -> list[dict]:
        """Find nodes closest to the given embedding vector (cosine distance)."""
        emb_str = str(embedding)
        if type_id is not None:
            rows = await self._pg.fetch(
                """SELECT id, type_id, name, content, properties, source, created_at, updated_at,
                          1 - (embedding <=> $1::vector) AS similarity
                   FROM node
                   WHERE embedding IS NOT NULL AND type_id = $2
                   ORDER BY embedding <=> $1::vector
                   LIMIT $3""",
                emb_str, type_id, limit,
            )
        else:
            rows = await self._pg.fetch(
                """SELECT id, type_id, name, content, properties, source, created_at, updated_at,
                          1 - (embedding <=> $1::vector) AS similarity
                   FROM node
                   WHERE embedding IS NOT NULL
                   ORDER BY embedding <=> $1::vector
                   LIMIT $2""",
                emb_str, limit,
            )
        return [dict(r) for r in rows]

    # ── Search: Full-Text (BM25 via tsvector) ────────────────────

    async def search_by_text(self, query: str, limit: int = 10, type_id: int | None = None) -> list[dict]:
        """Full-text search using PostgreSQL tsvector. Returns nodes ranked by ts_rank."""
        if type_id is not None:
            rows = await self._pg.fetch(
                """SELECT id, type_id, name, content, properties, source, created_at, updated_at,
                          ts_rank(tsv, plainto_tsquery('english', $1)) AS rank
                   FROM node
                   WHERE tsv @@ plainto_tsquery('english', $1) AND type_id = $2
                   ORDER BY rank DESC
                   LIMIT $3""",
                query, type_id, limit,
            )
        else:
            rows = await self._pg.fetch(
                """SELECT id, type_id, name, content, properties, source, created_at, updated_at,
                          ts_rank(tsv, plainto_tsquery('english', $1)) AS rank
                   FROM node
                   WHERE tsv @@ plainto_tsquery('english', $1)
                   ORDER BY rank DESC
                   LIMIT $2""",
                query, limit,
            )
        return [dict(r) for r in rows]

    # ── Search: Episodes by vector ───────────────────────────────

    async def search_episodes_by_vector(
        self, embedding: list[float], agent_id: str | None = None, limit: int = 10
    ) -> list[dict]:
        """Find episodes closest to the given embedding vector."""
        emb_str = str(embedding)
        if agent_id:
            rows = await self._pg.fetch(
                """SELECT id, agent_id, content, source_type, metadata, created_at,
                          1 - (embedding <=> $1::vector) AS similarity
                   FROM episode
                   WHERE embedding IS NOT NULL AND agent_id = $2
                   ORDER BY embedding <=> $1::vector
                   LIMIT $3""",
                emb_str, agent_id, limit,
            )
        else:
            rows = await self._pg.fetch(
                """SELECT id, agent_id, content, source_type, metadata, created_at,
                          1 - (embedding <=> $1::vector) AS similarity
                   FROM episode
                   WHERE embedding IS NOT NULL
                   ORDER BY embedding <=> $1::vector
                   LIMIT $2""",
                emb_str, limit,
            )
        return [dict(r) for r in rows]

    # ── Search: Graph-aware neighbor expansion ───────────────────

    async def search_with_neighbors(
        self, embedding: list[float], limit: int = 5
    ) -> list[dict]:
        """Vector search + expand results with immediate graph neighbors.
        Returns primary hits annotated with their neighbors."""
        hits = await self.search_by_vector(embedding, limit=limit)
        results = []
        for hit in hits:
            neighbors = await self.get_neighbors(hit["id"])
            hit["neighbors"] = neighbors
            results.append(hit)
        return results

    # ── Ontology stats (for `discover` MCP tool) ─────────────────

    async def get_ontology_stats(self) -> dict:
        """Return ontology overview: type counts, node counts per type, edge counts per type."""
        node_counts = await self._pg.fetch(
            """SELECT nt.name as type_name, count(n.id) as count
               FROM node_type nt
               LEFT JOIN node n ON n.type_id = nt.id
               GROUP BY nt.id, nt.name
               ORDER BY count DESC"""
        )
        edge_counts = await self._pg.fetch(
            """SELECT et.name as type_name, count(e.id) as count
               FROM edge_type et
               LEFT JOIN edge e ON e.type_id = et.id
               GROUP BY et.id, et.name
               ORDER BY count DESC"""
        )
        total_nodes = await self._pg.fetchval("SELECT count(*) FROM node")
        total_edges = await self._pg.fetchval("SELECT count(*) FROM edge")
        total_episodes = await self._pg.fetchval("SELECT count(*) FROM episode")
        return {
            "total_nodes": total_nodes,
            "total_edges": total_edges,
            "total_episodes": total_episodes,
            "node_types": [dict(r) for r in node_counts],
            "edge_types": [dict(r) for r in edge_counts],
        }
```

### Verification

- [ ] `uv run ruff check src/neocortex/` passes
- [ ] `uv run black --check src/neocortex/` passes
- [ ] Manual smoke test with Docker running: create a temporary script, run it, verify output, then delete it. It should create nodes with dummy 768-dim embeddings, then call `search_by_vector`, `search_by_text`, and `get_ontology_stats`.

```python
# /tmp/smoke_search.py (temporary — run then delete, do NOT commit)
import asyncio
from neocortex.postgres_service import PostgresService
from neocortex.graph_service import GraphService

async def main():
    async with PostgresService() as pg:
        gs = GraphService(pg)
        concept = await gs.get_node_type_by_name("Concept")

        # Create nodes with embeddings (768-dim dummy vectors)
        emb1 = [0.1] * 768
        emb2 = [0.2] * 768
        n1 = await gs.create_node(type_id=concept.id, name="PostgreSQL", content="Relational database with SQL", embedding=emb1)
        n2 = await gs.create_node(type_id=concept.id, name="pgvector", content="Vector similarity search extension", embedding=emb2)

        # Vector search
        results = await gs.search_by_vector([0.15] * 768, limit=5)
        print(f"Vector search: {[(r['name'], r['similarity']) for r in results]}")

        # Text search
        results = await gs.search_by_text("database SQL", limit=5)
        print(f"Text search: {[(r['name'], r['rank']) for r in results]}")

        # Ontology stats
        stats = await gs.get_ontology_stats()
        print(f"Stats: {stats}")

asyncio.run(main())
```

Run with `uv run python /tmp/smoke_search.py`. Expected: vector search returns VecA first, text search returns PostgreSQL first, stats show correct counts. Delete the script after verification.

### Commit

`feat(neocortex): add vector, full-text, and graph-aware search to GraphService`

---

## Stage 5: Integration Tests & Verification

**Goal**: Automated pytest suite validating all services against a real PostgreSQL instance. End-to-end verification of the complete storage layer.
**Dependencies**: Stage 4, Docker running

### Steps

#### 5.1 Create `tests/conftest.py` with shared fixtures

```python
import pytest_asyncio
from neocortex.config import PostgresConfig
from neocortex.postgres_service import PostgresService
from neocortex.graph_service import GraphService


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def pg_service():
    """Session-scoped PostgresService connected to the Docker PostgreSQL."""
    config = PostgresConfig()
    service = PostgresService(config)
    await service.connect()
    yield service
    await service.disconnect()


@pytest_asyncio.fixture(loop_scope="session")
async def graph_service(pg_service):
    """Per-test GraphService. Cleans up created test data after each test.

    IMPORTANT: All test data must follow naming conventions for cleanup:
    - Nodes: use source="test_<something>"
    - Episodes: use agent_id="test_<something>"
    - Node types: use name="Test_<Something>"
    - Edge types: use name="TEST_<SOMETHING>"
    """
    gs = GraphService(pg_service)
    yield gs
    # Cleanup: remove test data (edges cascade from nodes via ON DELETE CASCADE)
    await pg_service.execute("DELETE FROM episode WHERE agent_id LIKE 'test_%'")
    await pg_service.execute("DELETE FROM node WHERE source LIKE 'test_%'")
    await pg_service.execute("DELETE FROM node_type WHERE name LIKE 'Test_%'")
    await pg_service.execute("DELETE FROM edge_type WHERE name LIKE 'TEST_%'")
```

**Note**: This `conftest.py` only provides fixtures for neocortex integration tests. Existing tests in `tests/` (e.g., `test_agents.py`, `test_database.py`) are unaffected — they don't use these fixtures. If running `uv run pytest tests/ -v`, all tests (old and new) will run together; ensure Docker is up so neocortex tests pass.

#### 5.2 Create `tests/test_postgres_service.py`

```python
import pytest


@pytest.mark.asyncio
async def test_health_check(pg_service):
    health = await pg_service.health_check()
    assert health["status"] == "healthy"
    assert "vector" in health["extensions"]
    assert "pg_trgm" in health["extensions"]
    assert health["database"] == "neocortex"


@pytest.mark.asyncio
async def test_fetchval(pg_service):
    result = await pg_service.fetchval("SELECT 1 + 1")
    assert result == 2
```

#### 5.3 Create `tests/test_graph_ontology.py`

```python
import pytest


@pytest.mark.asyncio
async def test_seed_node_types_exist(graph_service):
    types = await graph_service.list_node_types()
    names = {t.name for t in types}
    assert "Concept" in names
    assert "Person" in names


@pytest.mark.asyncio
async def test_seed_edge_types_exist(graph_service):
    types = await graph_service.list_edge_types()
    names = {t.name for t in types}
    assert "RELATES_TO" in names
    assert "MENTIONS" in names


@pytest.mark.asyncio
async def test_create_and_get_node_type(graph_service):
    nt = await graph_service.create_node_type("Test_CustomType", "A test type")
    assert nt.name == "Test_CustomType"
    fetched = await graph_service.get_node_type(nt.id)
    assert fetched is not None
    assert fetched.name == "Test_CustomType"


@pytest.mark.asyncio
async def test_update_node_type(graph_service):
    nt = await graph_service.create_node_type("Test_Updateable", "Before")
    updated = await graph_service.update_node_type(nt.id, description="After")
    assert updated.description == "After"
    assert updated.name == "Test_Updateable"


@pytest.mark.asyncio
async def test_delete_node_type(graph_service):
    nt = await graph_service.create_node_type("Test_Deleteable", "To be deleted")
    assert await graph_service.delete_node_type(nt.id)
    assert await graph_service.get_node_type(nt.id) is None
```

#### 5.4 Create `tests/test_graph_data.py`

```python
import pytest


@pytest.mark.asyncio
async def test_create_and_get_node(graph_service):
    concept = await graph_service.get_node_type_by_name("Concept")
    node = await graph_service.create_node(
        type_id=concept.id, name="TestNode", content="Test content", source="test_data"
    )
    assert node.name == "TestNode"
    fetched = await graph_service.get_node(node.id)
    assert fetched is not None
    assert fetched.content == "Test content"


@pytest.mark.asyncio
async def test_create_node_with_embedding(graph_service):
    concept = await graph_service.get_node_type_by_name("Concept")
    emb = [0.1] * 768
    node = await graph_service.create_node(
        type_id=concept.id, name="EmbeddedNode", embedding=emb, source="test_data"
    )
    assert node.id > 0


@pytest.mark.asyncio
async def test_create_and_traverse_edge(graph_service):
    concept = await graph_service.get_node_type_by_name("Concept")
    relates = await graph_service.get_edge_type_by_name("RELATES_TO")
    n1 = await graph_service.create_node(type_id=concept.id, name="Node_A", source="test_data")
    n2 = await graph_service.create_node(type_id=concept.id, name="Node_B", source="test_data")
    edge = await graph_service.create_edge(source_id=n1.id, target_id=n2.id, type_id=relates.id)
    assert edge.source_id == n1.id
    assert edge.target_id == n2.id

    outgoing = await graph_service.get_edges_from(n1.id)
    assert len(outgoing) == 1
    assert outgoing[0].target_id == n2.id

    incoming = await graph_service.get_edges_to(n2.id)
    assert len(incoming) == 1
    assert incoming[0].source_id == n1.id


@pytest.mark.asyncio
async def test_get_neighbors(graph_service):
    concept = await graph_service.get_node_type_by_name("Concept")
    relates = await graph_service.get_edge_type_by_name("RELATES_TO")
    center = await graph_service.create_node(type_id=concept.id, name="Center", source="test_data")
    leaf = await graph_service.create_node(type_id=concept.id, name="Leaf", source="test_data")
    await graph_service.create_edge(source_id=center.id, target_id=leaf.id, type_id=relates.id)

    neighbors = await graph_service.get_neighbors(center.id)
    assert len(neighbors) >= 1
    assert any(n["name"] == "Leaf" for n in neighbors)


@pytest.mark.asyncio
async def test_create_and_list_episodes(graph_service):
    ep = await graph_service.create_episode(
        agent_id="test_agent", content="Test episode content", source_type="test"
    )
    assert ep.agent_id == "test_agent"
    episodes = await graph_service.list_episodes(agent_id="test_agent")
    assert len(episodes) >= 1
```

#### 5.5 Create `tests/test_graph_search.py`

```python
import pytest


@pytest.mark.asyncio
async def test_vector_search(graph_service):
    concept = await graph_service.get_node_type_by_name("Concept")
    emb_a = [1.0] + [0.0] * 767  # Unit vector in first dimension
    emb_b = [0.0, 1.0] + [0.0] * 766  # Unit vector in second dimension
    await graph_service.create_node(type_id=concept.id, name="VecA", embedding=emb_a, source="test_search")
    await graph_service.create_node(type_id=concept.id, name="VecB", embedding=emb_b, source="test_search")

    # Search near emb_a — should find VecA first
    results = await graph_service.search_by_vector([0.9, 0.1] + [0.0] * 766, limit=2)
    assert len(results) >= 1
    assert results[0]["name"] == "VecA"


@pytest.mark.asyncio
async def test_text_search(graph_service):
    concept = await graph_service.get_node_type_by_name("Concept")
    await graph_service.create_node(
        type_id=concept.id, name="PostgreSQL", content="Open source relational database management system",
        source="test_search",
    )
    await graph_service.create_node(
        type_id=concept.id, name="Redis", content="In-memory key-value data store",
        source="test_search",
    )

    results = await graph_service.search_by_text("relational database", limit=5)
    assert len(results) >= 1
    assert results[0]["name"] == "PostgreSQL"


@pytest.mark.asyncio
async def test_ontology_stats(graph_service):
    stats = await graph_service.get_ontology_stats()
    assert "total_nodes" in stats
    assert "total_edges" in stats
    assert "total_episodes" in stats
    assert "node_types" in stats
    assert "edge_types" in stats
    assert len(stats["node_types"]) >= 6  # seed types
```

#### 5.6 Add `pytest.ini` / configure pytest in `pyproject.toml`

Add to `pyproject.toml`:
```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "session"
testpaths = ["tests"]
```

### Verification

- [ ] Docker is running: `docker compose up -d` and container is healthy
- [ ] `uv run pytest tests/test_postgres_service.py tests/test_graph_ontology.py tests/test_graph_data.py tests/test_graph_search.py -v` — all tests pass
- [ ] `uv run ruff check src/neocortex/ tests/` passes
- [ ] `uv run black --check src/neocortex/ tests/` passes

### Commit

`test(neocortex): add integration tests for PostgresService and GraphService`

---

## Stage 6: Push to Remote

**Goal**: Push all committed changes from Stages 1-5 to the remote repository.
**Dependencies**: Stage 5 (all tests passing)

### Steps

#### 6.1 Verify all stages are DONE

Check the progress tracker above. All stages 1-5 must be DONE. If any stage is BLOCKED, do not push — stop and report.

#### 6.2 Verify clean working tree

```bash
git status
```

There should be no uncommitted changes (other than untracked files unrelated to this plan). If there are uncommitted changes related to this plan, something was missed — go back and fix.

#### 6.3 Verify commit history

```bash
git log --oneline -10
```

You should see 5 commits from this plan (one per stage). Verify the messages match the expected commits from each stage.

#### 6.4 Push to remote

```bash
git push origin main
```

If the push is rejected (e.g., remote has diverged), pull with rebase first:
```bash
git pull --rebase origin main
```

Then re-run the test suite (`uv run pytest tests/ -v`) to ensure the rebase didn't break anything, and push again.

### Verification

- [ ] `git push` succeeds without errors
- [ ] `git log --oneline -5` matches the expected commits from Stages 1-5
- [ ] Remote branch is up to date: `git status` shows "Your branch is up to date with 'origin/main'"

### Commit

No new commit — this stage only pushes existing commits.

---

## Overall Verification

After all stages are complete, run the full validation:

1. **Clean start**: `docker compose down -v && docker compose up -d` (destroy volume, recreate)
2. **Wait for healthy**: `docker compose ps` shows healthy
3. **Full test suite**: `uv run pytest tests/ -v` — all tests pass
4. **Persistence check**: `docker compose restart postgres` then re-run tests — data from seed survives restart
5. **Lint clean**: `uv run ruff check src/neocortex/ && uv run black --check src/neocortex/`

## Final File Tree

```
project-root/
├── docker-compose.yml
├── .env                              (gitignored, copy from .env.example)
├── .env.example                      (committed, documents required env vars)
├── migrations/
│   └── init/
│       ├── 001_extensions.sql
│       ├── 002_schema.sql
│       ├── 003_indexes.sql
│       └── 004_seed_ontology.sql
├── src/
│   └── neocortex/
│       ├── __init__.py
│       ├── config.py
│       ├── models.py
│       ├── postgres_service.py
│       └── graph_service.py
├── tests/
│   ├── conftest.py
│   ├── test_postgres_service.py
│   ├── test_graph_ontology.py
│   ├── test_graph_data.py
│   └── test_graph_search.py
└── pyproject.toml                    (updated)
```

## Issues

_None yet._

## Decisions

### Decision: Package location
- **Options**: A) New `src/neocortex/` package B) Extend `src/pydantic_agents_playground/`
- **Chosen**: A
- **Rationale**: Clean separation between POC playground and production storage layer. The playground was a proof of concept; NeoCortex is the real system.

### Decision: Migration approach
- **Options**: A) Raw SQL files in `migrations/init/`, applied by Docker on first start + `_migration` table for app-level B) Alembic
- **Chosen**: A
- **Rationale**: Minimal dependencies, full control over SQL, hackathon-appropriate simplicity. Schema changes tracked via `_migration` table for application-level migrations applied by `PostgresService.apply_migration()`.

### Decision: IVFFlat vs HNSW for vector indexes
- **Options**: A) IVFFlat (requires training, `lists=100`) B) HNSW (no training, works well on small data)
- **Chosen**: B (HNSW) with `m=16, ef_construction=64`
- **Rationale**: HNSW works correctly on empty tables (no training data needed), which is critical since Docker init scripts create indexes before any data exists. Performs well on small-to-medium datasets typical for a hackathon. Can switch to IVFFlat later for very large datasets if needed — it's just an index change, no schema migration required.

### Decision: Search methods scope
- **Options**: A) Basic building blocks only B) Full hybrid scoring with weighted formula
- **Chosen**: A — individual search methods (vector, text, neighbors) as composable building blocks
- **Rationale**: The weighted hybrid scoring formula (`0.4 * cosine + 0.3 * ts_rank + 0.3 * recency_decay`) belongs in the MCP server layer which orchestrates recall. The storage layer provides clean primitives.
