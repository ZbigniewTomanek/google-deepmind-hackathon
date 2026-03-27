-- =============================================================
-- NeoCortex Graph Schema Template
-- =============================================================
-- This file is a reference template loaded programmatically by SchemaManager.
-- It must not be placed under migrations/init/ because it is not an init migration.

CREATE SCHEMA IF NOT EXISTS {schema_name};

-- Ontology: what types of nodes exist
CREATE TABLE IF NOT EXISTS {schema_name}.node_type (
    id          SERIAL PRIMARY KEY,
    name        TEXT UNIQUE NOT NULL,
    description TEXT,
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- Ontology: what types of edges exist
CREATE TABLE IF NOT EXISTS {schema_name}.edge_type (
    id          SERIAL PRIMARY KEY,
    name        TEXT UNIQUE NOT NULL,
    description TEXT,
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- Graph nodes (entities/memories)
CREATE TABLE IF NOT EXISTS {schema_name}.node (
    id          SERIAL PRIMARY KEY,
    type_id     INT NOT NULL REFERENCES {schema_name}.node_type(id),
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
CREATE TABLE IF NOT EXISTS {schema_name}.edge (
    id          SERIAL PRIMARY KEY,
    source_id   INT NOT NULL REFERENCES {schema_name}.node(id) ON DELETE CASCADE,
    target_id   INT NOT NULL REFERENCES {schema_name}.node(id) ON DELETE CASCADE,
    type_id     INT NOT NULL REFERENCES {schema_name}.edge_type(id),
    weight      FLOAT DEFAULT 1.0,
    properties  JSONB DEFAULT '{}',
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- Episodic memory log (raw, append-only)
CREATE TABLE IF NOT EXISTS {schema_name}.episode (
    id          SERIAL PRIMARY KEY,
    agent_id    TEXT NOT NULL,
    content     TEXT NOT NULL,
    embedding   vector(768),
    source_type TEXT,
    metadata    JSONB DEFAULT '{}',
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- Migration tracking (for application-level migrations beyond init)
CREATE TABLE IF NOT EXISTS {schema_name}._migration (
    id          SERIAL PRIMARY KEY,
    name        TEXT UNIQUE NOT NULL,
    applied_at  TIMESTAMPTZ DEFAULT now()
);

-- Vector similarity search (cosine) on nodes — HNSW works on empty tables
CREATE INDEX IF NOT EXISTS idx_{schema_name}_node_embedding
    ON {schema_name}.node
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Full-text search (GIN) on auto-generated tsvector
CREATE INDEX IF NOT EXISTS idx_{schema_name}_node_tsv
    ON {schema_name}.node USING GIN (tsv);

-- Trigram index on node name for fuzzy matching
CREATE INDEX IF NOT EXISTS idx_{schema_name}_node_name_trgm
    ON {schema_name}.node USING GIN (name gin_trgm_ops);

-- Graph traversal indexes on edges
CREATE INDEX IF NOT EXISTS idx_{schema_name}_edge_source
    ON {schema_name}.edge (source_id);
CREATE INDEX IF NOT EXISTS idx_{schema_name}_edge_target
    ON {schema_name}.edge (target_id);
CREATE INDEX IF NOT EXISTS idx_{schema_name}_edge_type
    ON {schema_name}.edge (type_id);
CREATE INDEX IF NOT EXISTS idx_{schema_name}_edge_source_type
    ON {schema_name}.edge (source_id, type_id);

-- Episode lookup by agent + time
CREATE INDEX IF NOT EXISTS idx_{schema_name}_episode_agent
    ON {schema_name}.episode (agent_id, created_at DESC);

-- Vector similarity search on episodes — HNSW works on empty tables
CREATE INDEX IF NOT EXISTS idx_{schema_name}_episode_embedding
    ON {schema_name}.episode
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Node filtering by type
CREATE INDEX IF NOT EXISTS idx_{schema_name}_node_type
    ON {schema_name}.node (type_id);

-- Default node types
INSERT INTO {schema_name}.node_type (name, description) VALUES
    ('Concept',    'Abstract idea or topic'),
    ('Person',     'Human individual'),
    ('Document',   'Source document or file'),
    ('Event',      'Something that happened at a specific time'),
    ('Tool',       'Software tool, library, or technology'),
    ('Preference', 'User preference or opinion')
ON CONFLICT (name) DO NOTHING;

-- Default edge types
INSERT INTO {schema_name}.edge_type (name, description) VALUES
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

-- Conditionally populated by SchemaManager when provisioning shared graphs.
{rls_block}
