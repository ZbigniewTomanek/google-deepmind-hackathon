-- Node alias table for name variant resolution
CREATE TABLE IF NOT EXISTS node_alias (
    id          SERIAL PRIMARY KEY,
    node_id     INT NOT NULL REFERENCES node(id) ON DELETE CASCADE,
    alias       TEXT NOT NULL,
    source      TEXT DEFAULT 'extraction',  -- 'extraction', 'canonicalization', 'manual'
    created_at  TIMESTAMPTZ DEFAULT now(),
    UNIQUE (alias, node_id)  -- Prevent duplicate (alias, node) pairs; same alias CAN point to multiple nodes
);

-- Index for fast alias lookup (case-insensitive)
CREATE INDEX IF NOT EXISTS idx_node_alias_lower ON node_alias (lower(alias));
