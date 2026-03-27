-- =============================================================
-- Graph registry for multi-schema memory graphs
-- =============================================================

CREATE TABLE IF NOT EXISTS graph_registry (
    id          SERIAL PRIMARY KEY,
    agent_id    TEXT NOT NULL,
    purpose     TEXT NOT NULL,
    schema_name TEXT UNIQUE NOT NULL,
    is_shared   BOOLEAN DEFAULT FALSE,
    created_at  TIMESTAMPTZ DEFAULT now(),
    UNIQUE (agent_id, purpose)
);
