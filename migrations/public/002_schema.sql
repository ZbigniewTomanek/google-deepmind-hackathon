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
    id               SERIAL PRIMARY KEY,
    type_id          INT NOT NULL REFERENCES node_type(id),
    name             TEXT NOT NULL,
    content          TEXT,
    properties       JSONB DEFAULT '{}',
    embedding        vector(768),
    tsv              tsvector GENERATED ALWAYS AS (
                         to_tsvector('english', coalesce(name, '') || ' ' || coalesce(content, ''))
                     ) STORED,
    source           TEXT,
    access_count     INTEGER DEFAULT 0,
    last_accessed_at TIMESTAMPTZ DEFAULT now(),
    importance       FLOAT DEFAULT 0.5,
    forgotten        BOOLEAN DEFAULT false,
    forgotten_at     TIMESTAMPTZ,
    created_at       TIMESTAMPTZ DEFAULT now(),
    updated_at       TIMESTAMPTZ DEFAULT now()
);

-- Graph edges (relationships between nodes)
CREATE TABLE edge (
    id                  SERIAL PRIMARY KEY,
    source_id           INT NOT NULL REFERENCES node(id) ON DELETE CASCADE,
    target_id           INT NOT NULL REFERENCES node(id) ON DELETE CASCADE,
    type_id             INT NOT NULL REFERENCES edge_type(id),
    weight              FLOAT DEFAULT 1.0,
    properties          JSONB DEFAULT '{}',
    last_reinforced_at  TIMESTAMPTZ DEFAULT now(),
    created_at          TIMESTAMPTZ DEFAULT now(),
    UNIQUE (source_id, target_id, type_id)
);

-- Episodic memory log (raw, append-only)
CREATE TABLE episode (
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

-- Migration tracking (for application-level migrations beyond init)
CREATE TABLE IF NOT EXISTS _migration (
    id          SERIAL PRIMARY KEY,
    name        TEXT UNIQUE NOT NULL,
    applied_at  TIMESTAMPTZ DEFAULT now()
);
