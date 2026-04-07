# Database Schema & Diagnostic Queries

PostgreSQL schema reference and ready-to-run queries for debugging NeoCortex.

## Contents

- [Public Schema (Global Tables)](#public-schema-global-tables)
- [Per-Graph Schema (Template)](#per-graph-schema-template)
- [Schema Relationships](#schema-relationships)
- [Diagnostic Queries](#diagnostic-queries)

---

## Public Schema (Global Tables)

These tables live in the `public` schema and manage cross-graph coordination.

### graph_registry

Tracks all provisioned graph schemas.

```sql
CREATE TABLE graph_registry (
    id          SERIAL PRIMARY KEY,
    agent_id    TEXT NOT NULL,
    purpose     TEXT NOT NULL,
    schema_name TEXT UNIQUE NOT NULL,
    is_shared   BOOLEAN DEFAULT FALSE,
    created_at  TIMESTAMPTZ DEFAULT now(),
    UNIQUE (agent_id, purpose)
);
```

### agent_registry

Tracks known agents and admin status.

```sql
CREATE TABLE agent_registry (
    id          SERIAL PRIMARY KEY,
    agent_id    TEXT UNIQUE NOT NULL,
    is_admin    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now()
);
```

### graph_permissions

Per-agent, per-shared-schema access control.

```sql
CREATE TABLE graph_permissions (
    id          SERIAL PRIMARY KEY,
    agent_id    TEXT NOT NULL,
    schema_name TEXT NOT NULL REFERENCES graph_registry(schema_name) ON DELETE CASCADE,
    can_read    BOOLEAN NOT NULL DEFAULT FALSE,
    can_write   BOOLEAN NOT NULL DEFAULT FALSE,
    granted_by  TEXT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now(),
    UNIQUE (agent_id, schema_name)
);
```

### ontology_domains

Maps semantic domains to shared schemas. Seed rows auto-created on init.

```sql
CREATE TABLE ontology_domains (
    id          SERIAL PRIMARY KEY,
    slug        TEXT UNIQUE NOT NULL,
    name        TEXT NOT NULL,
    description TEXT NOT NULL,
    schema_name TEXT,            -- references graph_registry.schema_name (but no FK)
    seed        BOOLEAN DEFAULT false,
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now(),
    created_by  TEXT,
    parent_id   INTEGER REFERENCES ontology_domains(id),  -- hierarchy (Plan 30)
    depth       INTEGER NOT NULL DEFAULT 0,                -- 0 = root, 1 = child, etc.
    path        TEXT NOT NULL DEFAULT ''                    -- dot-separated slug path
);
-- Indexes: parent_id, path
```

**Seed domains:** `user_profile`, `technical_knowledge`, `work_context`, `domain_knowledge`.
Domains are hierarchical — `parent_id` links child domains to parents, `depth` tracks nesting level, `path` stores the dot-separated slug path (e.g., `domain_knowledge.film_and_media_studies`).

### node_type / edge_type (public)

Global ontology seed. Each graph schema also has its own copy.

```sql
CREATE TABLE node_type (
    id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL, description TEXT, created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE edge_type (
    id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL, description TEXT, created_at TIMESTAMPTZ DEFAULT now()
);
```

**Seed node types:** Concept, Person, Document, Event, Tool, Preference.
**Seed edge types:** RELATES_TO, MENTIONS, CAUSED_BY, FOLLOWS, AUTHORED, USES, CONTRADICTS, SUPPORTS, SUMMARIZES, DERIVED_FROM.

---

## Per-Graph Schema (Template)

Every graph (personal or shared) gets its own PG schema with these tables. Schema name pattern: `ncx_{owner}__{purpose}`.

### {schema}.node

```sql
CREATE TABLE {schema}.node (
    id               SERIAL PRIMARY KEY,
    type_id          INT NOT NULL REFERENCES {schema}.node_type(id),
    name             TEXT NOT NULL,
    content          TEXT,
    properties       JSONB DEFAULT '{}',
    embedding        vector(768),         -- Gemini MRL embeddings, cosine similarity
    tsv              tsvector GENERATED,   -- auto from name + content
    source           TEXT,
    access_count     INTEGER DEFAULT 0,
    last_accessed_at TIMESTAMPTZ DEFAULT now(),
    importance       FLOAT DEFAULT 0.5,
    forgotten        BOOLEAN DEFAULT false,
    forgotten_at     TIMESTAMPTZ,
    created_at       TIMESTAMPTZ DEFAULT now(),
    updated_at       TIMESTAMPTZ DEFAULT now()
);
```

### {schema}.edge

```sql
CREATE TABLE {schema}.edge (
    id                 SERIAL PRIMARY KEY,
    source_id          INT NOT NULL REFERENCES {schema}.node(id) ON DELETE CASCADE,
    target_id          INT NOT NULL REFERENCES {schema}.node(id) ON DELETE CASCADE,
    type_id            INT NOT NULL REFERENCES {schema}.edge_type(id),
    weight             FLOAT DEFAULT 1.0,    -- Hebbian reinforcement, ceiling 2.0
    properties         JSONB DEFAULT '{}',
    last_reinforced_at TIMESTAMPTZ DEFAULT now(),
    created_at         TIMESTAMPTZ DEFAULT now(),
    UNIQUE (source_id, target_id, type_id)
);
```

### {schema}.episode

```sql
CREATE TABLE {schema}.episode (
    id               SERIAL PRIMARY KEY,
    agent_id         TEXT NOT NULL,
    content          TEXT NOT NULL,
    embedding        vector(768),
    source_type      TEXT,
    metadata         JSONB DEFAULT '{}',
    access_count     INTEGER DEFAULT 0,
    last_accessed_at TIMESTAMPTZ DEFAULT now(),
    importance       FLOAT DEFAULT 0.5,
    consolidated     BOOLEAN DEFAULT false,
    created_at       TIMESTAMPTZ DEFAULT now()
);
```

### Key indexes per schema

- **HNSW** on `node.embedding` and `episode.embedding` (cosine, m=16, ef=64)
- **GIN** on `node.tsv` (full-text) and `node.name` (trigram)
- **B-tree** on `edge(source_id)`, `edge(target_id)`, `edge(source_id, type_id)`
- **Partial** on `node(forgotten) WHERE forgotten = false`
- **B-tree** on `episode(agent_id, created_at DESC)`

### Row-Level Security (shared schemas only)

Shared schemas add `owner_role TEXT` to node, edge, episode. RLS policies restrict reads/writes to rows matching `current_user`. The app uses `SET LOCAL ROLE agent_{id}` via `graph_scoped_connection()`.

---

## Diagnostic Queries

### System overview

```sql
-- List all graph schemas with sizes
SELECT schema_name, is_shared, agent_id, purpose, created_at
FROM graph_registry ORDER BY created_at;

-- Count nodes/edges/episodes across all schemas
SELECT schemaname AS schema,
       relname AS table_name,
       n_live_tup AS row_count
FROM pg_stat_user_tables
WHERE schemaname LIKE 'ncx_%'
ORDER BY schemaname, relname;

-- Quick summary: nodes, edges, episodes per schema
SELECT s.schema_name,
       (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON c.relnamespace = n.oid
        WHERE n.nspname = s.schema_name AND c.relname = 'node') AS has_node_table
FROM graph_registry s;
```

### Graph health

```sql
-- Node/edge/episode counts for a specific schema (replace SCHEMA)
SELECT 'nodes' AS entity, count(*) FROM SCHEMA.node
UNION ALL SELECT 'edges', count(*) FROM SCHEMA.edge
UNION ALL SELECT 'episodes', count(*) FROM SCHEMA.episode
UNION ALL SELECT 'node_types', count(*) FROM SCHEMA.node_type
UNION ALL SELECT 'edge_types', count(*) FROM SCHEMA.edge_type;

-- Nodes missing embeddings (extraction may have failed)
SELECT id, name, type_id, created_at
FROM SCHEMA.node WHERE embedding IS NULL ORDER BY created_at DESC LIMIT 20;

-- Orphaned nodes (no edges)
SELECT n.id, n.name, nt.name AS type
FROM SCHEMA.node n
JOIN SCHEMA.node_type nt ON n.type_id = nt.id
LEFT JOIN SCHEMA.edge e1 ON e1.source_id = n.id
LEFT JOIN SCHEMA.edge e2 ON e2.target_id = n.id
WHERE e1.id IS NULL AND e2.id IS NULL
ORDER BY n.created_at DESC LIMIT 20;

-- Forgotten nodes
SELECT id, name, importance, forgotten_at
FROM SCHEMA.node WHERE forgotten = true ORDER BY forgotten_at DESC;
```

### Ontology inspection

```sql
-- Node type distribution in a schema
SELECT nt.name AS type, count(*) AS cnt
FROM SCHEMA.node n JOIN SCHEMA.node_type nt ON n.type_id = nt.id
GROUP BY nt.name ORDER BY cnt DESC;

-- Edge type distribution
SELECT et.name AS type, count(*) AS cnt
FROM SCHEMA.edge e JOIN SCHEMA.edge_type et ON e.type_id = et.id
GROUP BY et.name ORDER BY cnt DESC;

-- Empty types (created but never used)
SELECT nt.name FROM SCHEMA.node_type nt
LEFT JOIN SCHEMA.node n ON n.type_id = nt.id
WHERE n.id IS NULL;

-- Ontology contamination check: types that look out-of-domain
-- (compare against seed types to find extraction-generated ones)
SELECT nt.name, nt.description, nt.created_at
FROM SCHEMA.node_type nt
WHERE nt.name NOT IN ('Concept','Person','Document','Event','Tool','Preference')
ORDER BY nt.created_at;
```

### Recall & search debugging

```sql
-- Test vector search (replace EMBEDDING with a 768-dim vector)
SELECT n.id, n.name, nt.name AS type,
       1 - (n.embedding <=> 'EMBEDDING') AS cosine_sim
FROM SCHEMA.node n
JOIN SCHEMA.node_type nt ON n.type_id = nt.id
WHERE n.forgotten = false AND n.embedding IS NOT NULL
ORDER BY n.embedding <=> 'EMBEDDING' LIMIT 10;

-- Test full-text search
SELECT n.id, n.name, ts_rank(n.tsv, q) AS rank
FROM SCHEMA.node n, plainto_tsquery('english', 'search terms here') q
WHERE n.tsv @@ q ORDER BY rank DESC LIMIT 10;

-- Test trigram fuzzy match on node name
SELECT n.id, n.name, similarity(n.name, 'fuzzy term') AS sim
FROM SCHEMA.node n
WHERE n.name % 'fuzzy term' ORDER BY sim DESC LIMIT 10;
```

### Edge weight & Hebbian reinforcement

```sql
-- Heaviest edges (most reinforced)
SELECT e.id, ns.name AS source, nt_node.name AS target,
       et.name AS edge_type, e.weight, e.last_reinforced_at
FROM SCHEMA.edge e
JOIN SCHEMA.node ns ON e.source_id = ns.id
JOIN SCHEMA.node nt_node ON e.target_id = nt_node.id
JOIN SCHEMA.edge_type et ON e.type_id = et.id
ORDER BY e.weight DESC LIMIT 20;

-- Edges at Hebbian ceiling (weight >= 2.0)
SELECT count(*) FROM SCHEMA.edge WHERE weight >= 2.0;
```

### Episode & extraction pipeline

```sql
-- Recent episodes
SELECT id, agent_id, source_type, left(content, 80) AS preview,
       metadata->>'source' AS source, created_at
FROM SCHEMA.episode ORDER BY created_at DESC LIMIT 20;

-- Episodes without embeddings
SELECT id, left(content, 60) AS preview, created_at
FROM SCHEMA.episode WHERE embedding IS NULL ORDER BY created_at DESC;

-- Episode count by source type
SELECT source_type, count(*) FROM SCHEMA.episode GROUP BY source_type;
```

### Permissions & access control

```sql
-- All permissions for a shared schema
SELECT gp.agent_id, gp.can_read, gp.can_write, gp.granted_by, gp.created_at
FROM graph_permissions gp
WHERE gp.schema_name = 'ncx_shared__SCHEMA_PURPOSE'
ORDER BY gp.agent_id;

-- Agents with admin status
SELECT agent_id, is_admin, created_at FROM agent_registry WHERE is_admin = true;

-- Domain routing configuration (with hierarchy)
SELECT slug, name, schema_name, seed, created_by, parent_id, depth, path
FROM ontology_domains ORDER BY path, id;

-- Domain tree view (parent-child relationships)
SELECT child.slug, child.name, child.depth, child.path, parent.slug AS parent_slug
FROM ontology_domains child
LEFT JOIN ontology_domains parent ON child.parent_id = parent.id
ORDER BY child.path;

-- Check if seed domain schemas actually exist
SELECT od.slug, od.schema_name,
       EXISTS(SELECT 1 FROM graph_registry gr WHERE gr.schema_name = od.schema_name) AS schema_exists
FROM ontology_domains od WHERE od.seed = true;
```

### Schema provisioning health

```sql
-- Schemas in graph_registry vs actual PG schemas
SELECT gr.schema_name, gr.is_shared,
       EXISTS(SELECT 1 FROM information_schema.schemata s WHERE s.schema_name = gr.schema_name) AS pg_schema_exists
FROM graph_registry gr;

-- PG schemas matching ncx_ pattern not in registry (orphaned)
SELECT s.schema_name
FROM information_schema.schemata s
LEFT JOIN graph_registry gr ON gr.schema_name = s.schema_name
WHERE s.schema_name LIKE 'ncx_%' AND gr.schema_name IS NULL;

-- List all ncx_ schemas with table counts
SELECT n.nspname AS schema, count(c.relname) AS table_count
FROM pg_namespace n
LEFT JOIN pg_class c ON c.relnamespace = n.oid AND c.relkind = 'r'
WHERE n.nspname LIKE 'ncx_%'
GROUP BY n.nspname ORDER BY n.nspname;
```
