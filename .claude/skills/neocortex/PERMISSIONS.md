# Permissions & Shared Graph Setup

How to configure agent roles and shared memory structures so ingested data lands in the right graphs.

## Contents

- [Architecture Overview](#architecture-overview)
- [Personal vs Shared Graphs](#personal-vs-shared-graphs)
- [Setup Workflow](#setup-workflow)
- [Domain Routing (Automatic)](#domain-routing-automatic)
- [Configuration Reference](#configuration-reference)
- [Troubleshooting](#troubleshooting)

---

## Architecture Overview

```
Agent (token) ──→ Personal graph: ncx_{agent_id}__memory (auto-created)
                 ├─→ Shared graph:  ncx_shared__purpose  (requires permission)
                 └─→ Domain graph:  ncx_shared__domain    (auto-routed)
```

- **Personal graphs** are created automatically on first use. No setup needed.
- **Shared graphs** require admin to create the graph and grant per-agent permissions.
- **Domain graphs** are auto-provisioned by the domain router when semantic classification matches.

Schema naming pattern: `ncx_{owner}__{purpose}` (double underscore separator). Validated by regex `^ncx_[a-z0-9]+__[a-z0-9_]+$`.

---

## Personal vs Shared Graphs

| Aspect | Personal | Shared |
|--------|----------|--------|
| Created | Automatically on first store | Admin creates via API |
| Schema name | `ncx_{agent_id}__memory` | `ncx_shared__{purpose}` |
| Write access | Owner only | Agents with `can_write=true` |
| Read access | Owner only | Agents with `can_read=true` |
| RLS (row-level security) | No | Yes (rows tagged with `row_owner`) |
| Ingestion | Default (no `target_graph`) | Must specify `target_graph` |

---

## Setup Workflow

### Step 1: Ensure auth mode is configured

```bash
# In .env or environment:
NEOCORTEX_AUTH_MODE=dev_token
NEOCORTEX_DEV_TOKENS_FILE=dev_tokens.json
```

Verify `dev_tokens.json` has entries for all agents:

```json
{
  "admin-token": "admin",
  "claude-code-work": "cc-work",
  "claude-code-private": "cc-private"
}
```

### Step 2: Create a shared graph (admin only)

```bash
curl -X POST localhost:8001/admin/graphs \
  -H "Authorization: Bearer admin-token" \
  -H "Content-Type: application/json" \
  -d '{"purpose": "team_knowledge"}'
# Creates: ncx_shared__team_knowledge
```

### Step 3: Grant permissions to agents

```bash
# Grant cc-work read + write
curl -X POST localhost:8001/admin/permissions \
  -H "Authorization: Bearer admin-token" \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "cc-work", "schema_name": "ncx_shared__team_knowledge", "can_read": true, "can_write": true}'

# Grant cc-private read-only
curl -X POST localhost:8001/admin/permissions \
  -H "Authorization: Bearer admin-token" \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "cc-private", "schema_name": "ncx_shared__team_knowledge", "can_read": true, "can_write": false}'
```

### Step 4: Ingest to shared graph

```bash
# cc-work can write:
curl -X POST localhost:8001/ingest/text \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer claude-code-work" \
  -d '{"text": "Team standup notes", "target_graph": "ncx_shared__team_knowledge"}'
# 200 OK

# cc-private cannot write:
curl -X POST localhost:8001/ingest/text \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer claude-code-private" \
  -d '{"text": "Attempt to write", "target_graph": "ncx_shared__team_knowledge"}'
# 403 Forbidden
```

### Step 5: Verify access

```bash
# List permissions
curl -s localhost:8001/admin/permissions?schema_name=ncx_shared__team_knowledge \
  -H "Authorization: Bearer admin-token" | python3 -m json.tool

# List all graphs
curl -s localhost:8001/admin/graphs \
  -H "Authorization: Bearer admin-token" | python3 -m json.tool
```

---

## Domain Routing (Automatic)

When `domain_routing_enabled=true` (default), the system automatically classifies ingested content and routes copies to semantically relevant shared domain graphs.

**How it works:**

1. Content is ingested to the agent's personal graph (always happens)
2. A classifier (Gemini model) assigns semantic domain labels with confidence scores
3. For each domain above the threshold (default 0.3), the system:
   - Auto-provisions a shared schema `ncx_shared__{domain_slug}` if it doesn't exist
   - Grants the originating agent read+write permission
   - Enqueues an extraction job targeting the shared schema

**Domain routing is additive** — it never replaces personal graph storage. When `target_graph` is explicitly set, domain routing is skipped (explicit beats automatic).

**Configuration:**

```bash
NEOCORTEX_DOMAIN_ROUTING_ENABLED=true         # Enable/disable
NEOCORTEX_DOMAIN_CLASSIFICATION_THRESHOLD=0.3  # Min confidence (0.0-1.0)
```

---

## Configuration Reference

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `NEOCORTEX_AUTH_MODE` | `"none"` | `"none"`, `"dev_token"`, `"google_oauth"` |
| `NEOCORTEX_DEV_TOKENS_FILE` | `""` | Path to token-to-agent JSON mapping |
| `NEOCORTEX_DEV_TOKEN` | `"dev-token-neocortex"` | Single dev token (deprecated fallback) |
| `NEOCORTEX_DEV_USER_ID` | `"dev-user"` | Agent ID for single dev token |
| `NEOCORTEX_ADMIN_TOKEN` | `"admin-token"` | Bootstrap admin bearer token |
| `NEOCORTEX_BOOTSTRAP_ADMIN_ID` | `"admin"` | Agent ID seeded as admin on startup |
| `NEOCORTEX_DOMAIN_ROUTING_ENABLED` | `true` | Auto-route to domain graphs |
| `NEOCORTEX_DOMAIN_CLASSIFICATION_THRESHOLD` | `0.3` | Min classification confidence |
| `NEOCORTEX_MEDIA_STORE_PATH` | `"./media_store"` | Compressed media file storage root |
| `NEOCORTEX_MEDIA_MAX_UPLOAD_BYTES` | `104857600` | Max media upload size (100 MB) |

### Admin Roles

- **Bootstrap admin**: Auto-created on every startup. Cannot be demoted. Configured via `NEOCORTEX_BOOTSTRAP_ADMIN_ID`.
- **Promoted admins**: Any agent promoted via `PUT /admin/agents/{id}/admin`. Can be demoted.
- **Admins bypass all permission checks** — they can read/write all shared schemas.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| 401 on ingestion | Token not in `dev_tokens.json` | Add token mapping to the file |
| 403 on `target_graph` | Agent lacks `can_write` permission | Admin must grant via `/admin/permissions` |
| 403 on `/admin/*` | Agent is not admin | Promote via `/admin/agents/{id}/admin` or use bootstrap admin token |
| 415 on document upload | Unsupported content type | Use one of: text/plain, application/json, text/markdown, text/csv |
| 413 on upload | File too large | Documents: 10 MB max. Media: 100 MB max |
| Data not in shared graph | Missing `target_graph` param | Add `"target_graph": "ncx_shared__purpose"` to request |
| Domain routing not working | Feature disabled or threshold too high | Check `NEOCORTEX_DOMAIN_ROUTING_ENABLED` and threshold |
