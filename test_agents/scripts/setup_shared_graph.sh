#!/usr/bin/env bash
# Setup shared research graph and permissions (idempotent).
# Run after NeoCortex services are up.
set -euo pipefail

ADMIN_TOKEN="${NEOCORTEX_ADMIN_TOKEN:-admin-token-neocortex}"
BASE_URL="${NEOCORTEX_INGESTION_URL:-http://localhost:8001}"

echo "=== Creating shared research graph ==="
# Create ncx_shared__research (ignore 409 if exists)
curl -sf -X POST "$BASE_URL/admin/graphs" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"purpose": "research"}' || true

echo ""
echo "=== Granting permissions to research agents ==="
# Grant read+write to all research agents
for agent in video-processor audio-processor rss-processor research-orch chat-extractions; do
  echo "  Granting access to $agent..."
  curl -sf -X POST "$BASE_URL/admin/permissions" \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"agent_id\": \"$agent\", \"schema_name\": \"ncx_shared__research\", \"can_read\": true, \"can_write\": true}" || true
done

echo ""
echo "=== Shared graph setup complete ==="
