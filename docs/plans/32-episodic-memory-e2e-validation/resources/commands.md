# Commands Reference

## Starting Services

```bash
# Fresh start (wipes DB, applies migrations)
./scripts/manage.sh start --fresh

# Normal start (preserves data)
./scripts/manage.sh start

# Check status
./scripts/manage.sh status

# Stop (keep PostgreSQL running)
./scripts/manage.sh stop

# Stop everything
./scripts/manage.sh stop --all
```

## Running the E2E Test

```bash
# Via unified runner (handles service lifecycle)
./scripts/run_e2e.sh scripts/e2e_episodic_memory_test.py

# Or manually with services already running
uv run python scripts/e2e_episodic_memory_test.py

# Keep services up after test for debugging
KEEP_RUNNING=1 ./scripts/run_e2e.sh scripts/e2e_episodic_memory_test.py
```

## Environment Variables

```bash
# Required for live server
export GOOGLE_API_KEY=...          # Gemini embeddings
export NEOCORTEX_AUTH_MODE=dev_token
export NEOCORTEX_DEV_TOKENS_FILE=dev_tokens.json
export NEOCORTEX_MOCK_DB=false

# Optional overrides
export NEOCORTEX_BASE_URL=http://127.0.0.1:8000
export NEOCORTEX_INGESTION_BASE_URL=http://127.0.0.1:8001
export NEOCORTEX_ALICE_TOKEN=alice-token
```

## Debugging Queries

```bash
# Connect to PostgreSQL
docker compose exec postgres psql -U neocortex

# Check episodes in personal schema
SELECT id, content, session_id, session_sequence, created_at
FROM "ncx_alice__personal".episode
ORDER BY created_at DESC LIMIT 20;

# Check FOLLOWS edges
SELECT e.id, e.source_id, e.target_id, et.name, e.weight
FROM "ncx_alice__personal".edge e
JOIN "ncx_alice__personal".edge_type et ON e.edge_type_id = et.id
WHERE et.name = 'FOLLOWS';

# Check extraction jobs
SELECT id, status, episode_id, created_at, completed_at
FROM "ncx_alice__personal".extraction_job
ORDER BY created_at DESC LIMIT 20;

# Check extracted nodes
SELECT id, name, nt.name as type_name, content
FROM "ncx_alice__personal".node n
JOIN "ncx_alice__personal".node_type nt ON n.node_type_id = nt.id
ORDER BY n.created_at DESC LIMIT 20;
```
