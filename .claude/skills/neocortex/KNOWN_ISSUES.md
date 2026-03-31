# Multi-Agent Setup & Debugging Guide

How to provision a working multi-agent NeoCortex deployment and debug common failures.

## Contents

- [Pre-Flight Checklist](#pre-flight-checklist)
- [Step 1: Configure Auth & Tokens](#step-1-configure-auth--tokens)
- [Step 2: Provision Seed Domain Schemas](#step-2-provision-seed-domain-schemas)
- [Step 3: Create Shared Graphs & Grant Permissions](#step-3-create-shared-graphs--grant-permissions)
- [Step 4: Verify Setup](#step-4-verify-setup)
- [Gotchas](#gotchas)
- [Debugging Workflows](#debugging-workflows)

---

## Pre-Flight Checklist

Before agents can share knowledge, three things must be true:

1. **Auth mode is set** — agents need distinct identities (`dev_token` or `google_oauth`)
2. **Seed domain schemas exist as real PG schemas** — migration 008 creates `ontology_domains` rows but does NOT provision the actual schemas (see Step 2)
3. **Permissions are granted** — each agent needs explicit `can_read`/`can_write` on every shared schema it should access

---

## Step 1: Configure Auth & Tokens

```bash
# .env or environment
NEOCORTEX_AUTH_MODE=dev_token
NEOCORTEX_DEV_TOKENS_FILE=dev_tokens.json
NEOCORTEX_BOOTSTRAP_ADMIN_ID=admin
```

Create `dev_tokens.json` with one entry per agent:

```json
{
  "admin-token": "admin",
  "claude-code-work": "cc-work",
  "claude-code-private": "cc-private"
}
```

Start services:

```bash
./scripts/manage.sh start
```

---

## Step 2: Provision Seed Domain Schemas

**This step is mandatory.** The seed migration writes domain rows to `ontology_domains` but never creates the corresponding PG schemas. Without this step, domain routing silently drops all classified content (`routed_to=[]`, no error).

```bash
SCRIPT="./.claude/skills/neocortex/scripts/ingest.sh"

# Provision all four seed domain schemas and grant admin access
for purpose in user_profile technical_knowledge work_context domain_knowledge; do
  $SCRIPT setup-shared "$purpose" admin
done
```

This creates:
- `ncx_shared__user_profile`
- `ncx_shared__technical_knowledge`
- `ncx_shared__work_context`
- `ncx_shared__domain_knowledge`

Each schema gets the full graph table set (node, edge, episode, node_type, edge_type) with indexes and seed ontology types.

---

## Step 3: Create Shared Graphs & Grant Permissions

Grant each agent access to the domain schemas they need:

```bash
SCRIPT="./.claude/skills/neocortex/scripts/ingest.sh"

# Grant alice read+write on all domain schemas
for purpose in user_profile technical_knowledge work_context domain_knowledge; do
  $SCRIPT grant alice "ncx_shared__${purpose}" rw
done

# Grant bob read-only on domain schemas
for purpose in user_profile technical_knowledge work_context domain_knowledge; do
  $SCRIPT grant bob "ncx_shared__${purpose}" r
done
```

For project-specific shared graphs (not domain-routed):

```bash
# Create a team graph and grant access
$SCRIPT setup-shared team_knowledge alice
$SCRIPT grant bob ncx_shared__team_knowledge rw
```

Permission modes: `rw` (read+write), `r` (read-only), `w` (write-only).

---

## Step 4: Verify Setup

```bash
SCRIPT="./.claude/skills/neocortex/scripts/ingest.sh"

# List all graphs — should show all provisioned schemas
$SCRIPT list-graphs

# List all permissions — should show grants for every agent
$SCRIPT list-permissions

# Test ingestion as alice
$SCRIPT --token claude-code-work text "Test fact from cc-work"

# Test domain routing — should appear in personal + domain schemas
$SCRIPT --token claude-code-work text "I prefer using Python for data science projects"
```

SQL verification:

```sql
-- Verify seed schemas are provisioned
SELECT od.slug, od.schema_name,
       EXISTS(SELECT 1 FROM graph_registry gr WHERE gr.schema_name = od.schema_name) AS in_registry,
       EXISTS(SELECT 1 FROM information_schema.schemata s WHERE s.schema_name = od.schema_name) AS pg_exists
FROM ontology_domains od WHERE od.seed = true;

-- All four should show in_registry=true AND pg_exists=true

-- Verify permissions
SELECT gp.agent_id, gp.schema_name, gp.can_read, gp.can_write
FROM graph_permissions gp ORDER BY gp.agent_id, gp.schema_name;
```

---

## Gotchas

| Gotcha | Symptom | Prevention |
|--------|---------|------------|
| Seed schemas not provisioned | Domain routing returns `routed_to=[]`, no error | Always run Step 2 after fresh DB init |
| `target_graph` skips domain routing | Content only lands in the explicit target, not domain schemas | Omit `target_graph` when you want automatic domain routing |
| Admin bypasses all permission checks | Admin sees all data even without grants | Use non-admin tokens for testing agent isolation |
| Media uploads without MIME type | 415 Unsupported Media Type | Use `ingest.sh` (auto-detects) or specify `type=audio/mpeg` in curl `-F` |
| Ontology contamination in shared graphs | Entities get wrong types (e.g., "Serotonin" as "DatabaseSystem") | Known issue — extraction agent force-fits existing types without domain context |

---

## Debugging Workflows

### "Ingested data isn't showing up in recall"

1. Check episode was stored: `SELECT * FROM SCHEMA.episode ORDER BY created_at DESC LIMIT 5;`
2. Check extraction ran: look for the episode's nodes in `SCHEMA.node`
3. Check embedding exists: `SELECT id, name, embedding IS NOT NULL FROM SCHEMA.node ORDER BY created_at DESC LIMIT 10;`
4. Check recall fan-out: does the agent have `can_read` on the target schema?
5. Check logs: `grep "recall" log/mcp.log | tail -20`

### "Domain routing isn't working"

1. Verify seed schemas are provisioned (Step 2 above)
2. Verify `NEOCORTEX_DOMAIN_ROUTING_ENABLED=true` (default)
3. Check classification threshold: `NEOCORTEX_DOMAIN_CLASSIFICATION_THRESHOLD` (default 0.3)
4. Check logs: `grep "domain_classification" log/ingestion.log | tail -10`
5. Verify permissions: `SELECT * FROM graph_permissions WHERE schema_name LIKE 'ncx_shared__%';`

### "Permission denied on shared graph"

1. Verify agent exists: `SELECT * FROM agent_registry WHERE agent_id = 'AGENT';`
2. Check permissions: `SELECT * FROM graph_permissions WHERE agent_id = 'AGENT';`
3. Check schema exists: `SELECT * FROM graph_registry WHERE schema_name = 'SCHEMA_NAME';`
4. Admin bypass: `SELECT * FROM agent_registry WHERE is_admin = true;`

### "Extraction produces wrong types"

1. Inspect the ontology: `SELECT name, description FROM SCHEMA.node_type ORDER BY name;`
2. Find non-seed types: `SELECT name FROM SCHEMA.node_type WHERE name NOT IN ('Concept','Person','Document','Event','Tool','Preference');`
3. Check extraction logs: `grep "extraction" log/ingestion.log | tail -20`
