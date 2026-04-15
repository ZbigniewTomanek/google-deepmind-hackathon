-- Plan 31, Stage 1: add session grouping to per-agent graph episodes table
ALTER TABLE {schema}.episode
    ADD COLUMN IF NOT EXISTS session_id TEXT,
    ADD COLUMN IF NOT EXISTS session_sequence INTEGER;

CREATE INDEX IF NOT EXISTS idx_episode_session
    ON {schema}.episode (agent_id, session_id, session_sequence, created_at, id)
    WHERE session_id IS NOT NULL;

-- Used by personal FOLLOWS creation in Stage 2. Compare as text in queries.
CREATE INDEX IF NOT EXISTS idx_node_source_episode
    ON {schema}.node ((properties->>'_source_episode'));
