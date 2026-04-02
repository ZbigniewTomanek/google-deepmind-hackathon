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
