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

-- Node filtering by type
CREATE INDEX idx_node_type ON node (type_id);

-- Partial index for fast filtering of non-forgotten nodes
CREATE INDEX idx_node_forgotten ON node (forgotten) WHERE forgotten = false;
