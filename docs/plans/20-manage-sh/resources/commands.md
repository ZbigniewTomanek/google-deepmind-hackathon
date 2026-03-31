# Commands Reference

## Docker / PostgreSQL

```bash
# Start PG (preserve volume)
docker compose -f docker-compose.yml up -d postgres

# Start PG (fresh volume)
docker compose -f docker-compose.yml down -v
docker compose -f docker-compose.yml up -d postgres

# Stop PG (keep volume)
docker compose -f docker-compose.yml down

# Stop PG (destroy volume)
docker compose -f docker-compose.yml down -v

# Check PG health
docker compose -f docker-compose.yml exec -T postgres pg_isready -U neocortex -d neocortex

# pg_dump (full DB, clean restore)
docker compose -f docker-compose.yml exec -T -e PGPASSWORD=neocortex postgres \
  pg_dump -U neocortex -d neocortex --clean --if-exists

# pg_restore via psql (pipe SQL in)
gunzip -c db.sql.gz | docker compose -f docker-compose.yml exec -T \
  -e PGPASSWORD=neocortex postgres psql -U neocortex -d neocortex

# Apply single migration
docker compose -f docker-compose.yml exec -T -e PGPASSWORD=neocortex postgres \
  psql -U neocortex -d neocortex < migrations/init/001_extensions.sql

# Check migration status
docker compose -f docker-compose.yml exec -T postgres \
  psql -U neocortex -d neocortex -tAc "SELECT name FROM _migration ORDER BY applied_at;"

# List graph schemas
docker compose -f docker-compose.yml exec -T postgres \
  psql -U neocortex -d neocortex -tAc "SELECT schema_name, agent_id, purpose FROM graph_registry;"
```

## Service Startup

```bash
# MCP server
NEOCORTEX_AUTH_MODE=dev_token \
NEOCORTEX_DEV_TOKENS_FILE=dev_tokens.json \
NEOCORTEX_MOCK_DB=false \
uv run python -m neocortex

# Ingestion server
NEOCORTEX_AUTH_MODE=dev_token \
NEOCORTEX_DEV_TOKENS_FILE=dev_tokens.json \
NEOCORTEX_MOCK_DB=false \
uv run python -m neocortex.ingestion
```

## Health Checks

```bash
curl -sf http://127.0.0.1:8000/health   # MCP
curl -sf http://127.0.0.1:8001/health   # Ingestion
```

## Snapshot Archive Format

```
<name>-<YYYYMMDD-HHMMSS>.tar.gz
├── snapshot.json      # metadata (name, date, has_media, pg_version)
├── db.sql.gz          # pg_dump --clean --if-exists | gzip
└── media_store/       # optional: copy of ./media_store/
```
