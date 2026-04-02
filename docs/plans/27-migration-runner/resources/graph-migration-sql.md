# Graph Migration SQL Reference

Reference SQL for the `migrations/graph/` files created in Stage 1.
These are derived from the current `migrations/templates/graph_schema.sql`.

**Placeholder**: All occurrences of `{schema_name}` in the old template become
`{schema}` in the new files (shorter, consistent with runner API).

---

## 001_base_tables.sql

```sql
-- NeoCortex per-schema graph tables
-- Applied by MigrationRunner.run_for_schema()

CREATE SCHEMA IF NOT EXISTS {schema};

-- Ontology: what types of nodes exist
CREATE TABLE IF NOT EXISTS {schema}.node_type (
    id          SERIAL PRIMARY KEY,
    name        TEXT UNIQUE NOT NULL,
    description TEXT,
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- Ontology: what types of edges exist
CREATE TABLE IF NOT EXISTS {schema}.edge_type (
    id          SERIAL PRIMARY KEY,
    name        TEXT UNIQUE NOT NULL,
    description TEXT,
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- Graph nodes (entities/memories)
CREATE TABLE IF NOT EXISTS {schema}.node (
    id              SERIAL PRIMARY KEY,
    type_id         INT NOT NULL REFERENCES {schema}.node_type(id),
    name            TEXT NOT NULL,
    content         TEXT,
    properties      JSONB DEFAULT '{}',
    embedding       vector(768),
    tsv             tsvector GENERATED ALWAYS AS (
                        to_tsvector('english', coalesce(name, '') || ' ' || coalesce(content, ''))
                    ) STORED,
    source          TEXT,
    access_count    INTEGER DEFAULT 0,
    last_accessed_at TIMESTAMPTZ DEFAULT now(),
    importance      FLOAT DEFAULT 0.5,
    forgotten       BOOLEAN DEFAULT false,
    forgotten_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

-- Node aliases for name variant resolution
CREATE TABLE IF NOT EXISTS {schema}.node_alias (
    id          SERIAL PRIMARY KEY,
    node_id     INT NOT NULL REFERENCES {schema}.node(id) ON DELETE CASCADE,
    alias       TEXT NOT NULL,
    source      TEXT DEFAULT 'extraction',
    created_at  TIMESTAMPTZ DEFAULT now(),
    UNIQUE (alias, node_id)
);

-- Graph edges (relationships between nodes)
CREATE TABLE IF NOT EXISTS {schema}.edge (
    id                  SERIAL PRIMARY KEY,
    source_id           INT NOT NULL REFERENCES {schema}.node(id) ON DELETE CASCADE,
    target_id           INT NOT NULL REFERENCES {schema}.node(id) ON DELETE CASCADE,
    type_id             INT NOT NULL REFERENCES {schema}.edge_type(id),
    weight              FLOAT DEFAULT 1.0,
    properties          JSONB DEFAULT '{}',
    last_reinforced_at  TIMESTAMPTZ DEFAULT now(),
    created_at          TIMESTAMPTZ DEFAULT now(),
    UNIQUE (source_id, target_id, type_id)
);

-- Episodic memory log (raw, append-only)
CREATE TABLE IF NOT EXISTS {schema}.episode (
    id              SERIAL PRIMARY KEY,
    agent_id        TEXT NOT NULL,
    content         TEXT NOT NULL,
    embedding       vector(768),
    source_type     TEXT,
    content_hash    TEXT,
    metadata        JSONB DEFAULT '{}',
    access_count    INTEGER DEFAULT 0,
    last_accessed_at TIMESTAMPTZ DEFAULT now(),
    importance      FLOAT DEFAULT 0.5,
    consolidated    BOOLEAN DEFAULT false,
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- Migration tracking (per-schema)
CREATE TABLE IF NOT EXISTS {schema}._migration (
    id          SERIAL PRIMARY KEY,
    name        TEXT UNIQUE NOT NULL,
    checksum    TEXT,
    applied_at  TIMESTAMPTZ DEFAULT now()
);
```

---

## 002_indexes.sql

```sql
-- NeoCortex per-schema indexes

-- Vector similarity search (cosine) on nodes
CREATE INDEX IF NOT EXISTS idx_{schema}_node_embedding
    ON {schema}.node
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Full-text search (GIN) on auto-generated tsvector
CREATE INDEX IF NOT EXISTS idx_{schema}_node_tsv
    ON {schema}.node USING GIN (tsv);

-- Trigram index on node name for fuzzy matching
CREATE INDEX IF NOT EXISTS idx_{schema}_node_name_trgm
    ON {schema}.node USING GIN (name gin_trgm_ops);

-- Alias lookup (case-insensitive)
CREATE INDEX IF NOT EXISTS idx_{schema}_node_alias_lower
    ON {schema}.node_alias (lower(alias));

-- Graph traversal indexes on edges
CREATE INDEX IF NOT EXISTS idx_{schema}_edge_source
    ON {schema}.edge (source_id);
CREATE INDEX IF NOT EXISTS idx_{schema}_edge_target
    ON {schema}.edge (target_id);
CREATE INDEX IF NOT EXISTS idx_{schema}_edge_type
    ON {schema}.edge (type_id);
CREATE INDEX IF NOT EXISTS idx_{schema}_edge_source_type
    ON {schema}.edge (source_id, type_id);

-- Episode lookup by agent + time
CREATE INDEX IF NOT EXISTS idx_{schema}_episode_agent
    ON {schema}.episode (agent_id, created_at DESC);

-- Vector similarity search on episodes
CREATE INDEX IF NOT EXISTS idx_{schema}_episode_embedding
    ON {schema}.episode
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Content hash for ingestion deduplication
CREATE INDEX IF NOT EXISTS idx_{schema}_episode_content_hash
    ON {schema}.episode (agent_id, content_hash)
    WHERE content_hash IS NOT NULL;

-- Node filtering by type
CREATE INDEX IF NOT EXISTS idx_{schema}_node_type
    ON {schema}.node (type_id);

-- Partial index for fast filtering of non-forgotten nodes
CREATE INDEX IF NOT EXISTS idx_{schema}_node_forgotten
    ON {schema}.node (forgotten) WHERE forgotten = false;
```

---

## 003_seed_ontology.sql

```sql
-- Default node types
INSERT INTO {schema}.node_type (name, description) VALUES
    ('Concept',    'Abstract idea or topic'),
    ('Person',     'Human individual'),
    ('Document',   'Source document or file'),
    ('Event',      'Something that happened at a specific time'),
    ('Tool',       'Software tool, library, or technology'),
    ('Preference', 'User preference or opinion')
ON CONFLICT (name) DO NOTHING;

-- Default edge types
INSERT INTO {schema}.edge_type (name, description) VALUES
    ('RELATES_TO',   'General relationship'),
    ('MENTIONS',     'Source mentions target'),
    ('CAUSED_BY',    'Target caused source'),
    ('FOLLOWS',      'Source follows target in sequence'),
    ('AUTHORED',     'Source authored target'),
    ('USES',         'Source uses target'),
    ('CONTRADICTS',  'Source contradicts target'),
    ('SUPPORTS',     'Source supports/confirms target'),
    ('SUMMARIZES',   'Source is a summary of target'),
    ('DERIVED_FROM', 'Source was derived from target'),
    ('SUPERSEDES',   'Source supersedes/replaces target — target is outdated'),
    ('CORRECTS',     'Source corrects an error or misconception in target')
ON CONFLICT (name) DO NOTHING;
```

---

## 004_node_alias.sql

```sql
-- No-op: node_alias table is included in 001_base_tables.sql for new schemas.
-- This file exists for legacy compatibility with schemas that tracked
-- '009_node_alias' as a separate migration.
SELECT 1;
```

---

## 005_content_hash.sql

```sql
-- No-op: content_hash column is included in 001_base_tables.sql for new schemas.
-- This file exists for legacy compatibility with schemas that tracked
-- '011_episode_content_hash' as a separate migration.
SELECT 1;
```
