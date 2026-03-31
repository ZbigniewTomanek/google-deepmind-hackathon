# Multi-Agent Architecture

NeoCortex supports multiple agents with isolated personal memory and optional shared knowledge graphs. Each agent gets its own PostgreSQL schema; shared schemas enable cross-agent knowledge with fine-grained permissions.

## Personal Graphs

Every agent automatically gets a personal graph on first use. The schema is provisioned lazily — no setup required.

```
Agent "cc-work" → schema ncx_cc_work__personal
Agent "cc-private" → schema ncx_cc_private__personal
```

Personal graphs are fully isolated. Agent A cannot see Agent B's personal data. Isolation is enforced at the PostgreSQL schema level via `SET LOCAL search_path`.

## Shared Graphs

Shared graphs enable cross-agent knowledge bases. Access is controlled by app-level permissions (`graph_permissions` table + `PermissionChecker`), allowing any authorized agent to read from and write to the same schema — including updating other agents' contributions for knowledge consolidation.

```
ncx_shared__technical_knowledge    — programming, tools, architecture
ncx_shared__domain_knowledge       — industry facts, concepts
ncx_shared__work_context           — projects, tasks, deadlines
```

Shared graphs must be created explicitly via the Admin API, and agents need permission grants to access them.

## Schema Naming Convention

All schemas follow the pattern `ncx_{owner}__{purpose}` (double underscore separator):

| Pattern | Example | Type |
|---------|---------|------|
| `ncx_{agent_id}__personal` | `ncx_cc_work__personal` | Per-agent (auto-created) |
| `ncx_shared__{purpose}` | `ncx_shared__technical_knowledge` | Shared (admin-created) |

Schema names are validated against `^ncx_[a-z0-9]+__[a-z0-9_]+$`.

## Routing

The `GraphRouter` decides which schemas to target for each operation:

| Operation | Routing |
|-----------|---------|
| `remember` (no target_graph) | Personal graph only |
| `remember` (target_graph set) | Specified shared graph (permission checked) |
| `recall` | Fan-out across personal + all readable shared graphs |
| `discover` | Aggregate across all accessible graphs |

When recalling, results from all accessible graphs are merged and scored together. The agent doesn't need to know which graph a memory lives in.

## Domain Routing

Domain routing automatically classifies memories into shared semantic domains. When an agent calls `remember(...)`, the text is classified by an LLM-based classifier into one or more domains:

### Seed Domains

| Domain | Description |
|--------|-------------|
| `user_profile` | Preferences, goals, habits, communication style |
| `technical_knowledge` | Programming, frameworks, APIs, architecture |
| `work_context` | Projects, tasks, deadlines, teams |
| `domain_knowledge` | Industry facts, concepts, trends |

### How It Works

1. Agent calls `remember("Python's asyncio is great for I/O-bound tasks")`
2. Episode stored in personal graph (immediate)
3. Domain classifier labels it `technical_knowledge` (confidence: 0.9)
4. Extraction job enqueued for the shared `ncx_shared__technical_knowledge` schema
5. Extraction pipeline runs with domain-specific hints
6. Knowledge appears in both personal and shared graphs

Domain routing is **additive** — it never replaces personal graph extraction. When `target_graph` is explicitly set on a `remember` call, domain routing is skipped (explicit beats automatic).

New domains can be proposed by the classifier and auto-provisioned (schema created, permissions granted).

### Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `NEOCORTEX_DOMAIN_ROUTING_ENABLED` | `true` | Enable/disable domain routing |
| `NEOCORTEX_DOMAIN_CLASSIFICATION_THRESHOLD` | `0.3` | Minimum confidence to route |
| `NEOCORTEX_DOMAIN_CLASSIFIER_MODEL` | `google-gla:gemini-3-flash-preview` | Classification model (any Pydantic AI provider string) |

## Permissions

Access to shared graphs is controlled by explicit permission grants:

| Permission | Effect |
|-----------|--------|
| `can_read` | Agent can recall from the shared graph |
| `can_write` | Agent can remember into the shared graph |

### Managing Permissions

Permissions are managed via the Admin API (on the ingestion server, port 8001):

```bash
# Grant read+write to an agent
curl -X POST localhost:8001/admin/permissions \
  -H "Authorization: Bearer admin-token" \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "cc-work", "schema_name": "ncx_shared__technical_knowledge", "can_read": true, "can_write": true}'

# List permissions for an agent
curl localhost:8001/admin/permissions/cc-work \
  -H "Authorization: Bearer admin-token"

# Revoke
curl -X DELETE localhost:8001/admin/permissions/cc-work/ncx_shared__technical_knowledge \
  -H "Authorization: Bearer admin-token"
```

### Admin Role

Admin agents bypass all permission checks. The bootstrap admin is seeded on every startup from `NEOCORTEX_BOOTSTRAP_ADMIN_ID` (default: `admin`). Additional admins can be promoted via:

```bash
curl -X PUT localhost:8001/admin/agents/cc-work/admin \
  -H "Authorization: Bearer admin-token"
```

## Shared Graph Lifecycle

```bash
# Create a shared graph
curl -X POST localhost:8001/admin/graphs \
  -H "Authorization: Bearer admin-token" \
  -H "Content-Type: application/json" \
  -d '{"purpose": "team_decisions", "is_shared": true}'

# List all graphs
curl localhost:8001/admin/graphs \
  -H "Authorization: Bearer admin-token"

# Drop a shared graph
curl -X DELETE localhost:8001/admin/graphs/ncx_shared__team_decisions \
  -H "Authorization: Bearer admin-token"
```
