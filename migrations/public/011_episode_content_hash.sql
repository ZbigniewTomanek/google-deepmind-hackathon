-- Add content hash for ingestion deduplication
ALTER TABLE episode ADD COLUMN IF NOT EXISTS content_hash TEXT;
CREATE INDEX IF NOT EXISTS idx_episode_content_hash
    ON episode (agent_id, content_hash)
    WHERE content_hash IS NOT NULL;
