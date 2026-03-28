-- Agent registry: tracks known agents and admin status
CREATE TABLE IF NOT EXISTS agent_registry (
    id          SERIAL PRIMARY KEY,
    agent_id    TEXT UNIQUE NOT NULL,
    is_admin    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_agent_registry_agent ON agent_registry (agent_id);

-- Graph-level permissions: per-agent, per-shared-schema access control
-- NOTE: agent_id intentionally has no FK to agent_registry to support
-- pre-provisioning permissions before an agent first connects.
CREATE TABLE IF NOT EXISTS graph_permissions (
    id          SERIAL PRIMARY KEY,
    agent_id    TEXT NOT NULL,
    schema_name TEXT NOT NULL REFERENCES graph_registry(schema_name) ON DELETE CASCADE,
    can_read    BOOLEAN NOT NULL DEFAULT FALSE,
    can_write   BOOLEAN NOT NULL DEFAULT FALSE,
    granted_by  TEXT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now(),
    UNIQUE (agent_id, schema_name)
);

CREATE INDEX IF NOT EXISTS idx_graph_permissions_agent ON graph_permissions (agent_id);
CREATE INDEX IF NOT EXISTS idx_graph_permissions_schema ON graph_permissions (schema_name);
