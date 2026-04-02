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
