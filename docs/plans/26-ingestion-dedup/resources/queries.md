# Queries & SQL Reference

## Hash Check Query (per-schema)

```sql
-- Check which hashes already exist for an agent in a given schema
SELECT content_hash, id
FROM {schema_name}.episode
WHERE agent_id = $1
  AND content_hash = ANY($2);
```

## Migration SQL (public schema)

```sql
ALTER TABLE episode ADD COLUMN IF NOT EXISTS content_hash TEXT;
CREATE INDEX IF NOT EXISTS idx_episode_content_hash
    ON episode (agent_id, content_hash)
    WHERE content_hash IS NOT NULL;
```

## Migration SQL (per-agent schema)

```sql
ALTER TABLE {schema_name}.episode ADD COLUMN IF NOT EXISTS content_hash TEXT;
CREATE INDEX IF NOT EXISTS idx_{schema_name}_episode_content_hash
    ON {schema_name}.episode (agent_id, content_hash)
    WHERE content_hash IS NOT NULL;
```

## Diagnostic: Check for duplicate episodes

```sql
-- Find duplicate episodes by content hash
SELECT content_hash, agent_id, COUNT(*) as copies, array_agg(id) as episode_ids
FROM {schema_name}.episode
WHERE content_hash IS NOT NULL
GROUP BY content_hash, agent_id
HAVING COUNT(*) > 1
ORDER BY copies DESC;
```

## Hash Computation (Python)

```python
import hashlib

def compute_content_hash(content: str) -> str:
    """Hash text content (text ingestion, events)."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()

def compute_content_hash_bytes(data: bytes) -> str:
    """Hash raw bytes (documents, audio, video uploads)."""
    return hashlib.sha256(data).hexdigest()
```
