-- Plan 31, Stage 1: add session grouping to public episodes table
ALTER TABLE episode
    ADD COLUMN IF NOT EXISTS session_id TEXT,
    ADD COLUMN IF NOT EXISTS session_sequence INTEGER;

CREATE INDEX IF NOT EXISTS idx_episode_session
    ON episode (agent_id, session_id, session_sequence, created_at, id)
    WHERE session_id IS NOT NULL;
