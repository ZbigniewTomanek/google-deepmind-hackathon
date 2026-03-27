-- =============================================================
-- Row-Level Security & Role-Based Access
-- =============================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'neocortex_agent') THEN
        CREATE ROLE neocortex_agent NOLOGIN;
    END IF;
END
$$;

GRANT USAGE ON SCHEMA public TO neocortex_agent;
GRANT SELECT, INSERT, UPDATE, DELETE ON node, edge, episode TO neocortex_agent;
GRANT SELECT, INSERT ON node_type, edge_type TO neocortex_agent;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO neocortex_agent;

ALTER TABLE node ADD COLUMN IF NOT EXISTS owner_role TEXT DEFAULT current_user;
ALTER TABLE edge ADD COLUMN IF NOT EXISTS owner_role TEXT DEFAULT current_user;
ALTER TABLE episode ADD COLUMN IF NOT EXISTS owner_role TEXT DEFAULT current_user;

CREATE INDEX IF NOT EXISTS idx_node_owner ON node (owner_role);
CREATE INDEX IF NOT EXISTS idx_edge_owner ON edge (owner_role);
CREATE INDEX IF NOT EXISTS idx_episode_owner ON episode (owner_role);

ALTER TABLE node ENABLE ROW LEVEL SECURITY;
ALTER TABLE edge ENABLE ROW LEVEL SECURITY;
ALTER TABLE episode ENABLE ROW LEVEL SECURITY;

ALTER TABLE node FORCE ROW LEVEL SECURITY;
ALTER TABLE edge FORCE ROW LEVEL SECURITY;
ALTER TABLE episode FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS node_select_policy ON node;
DROP POLICY IF EXISTS node_insert_policy ON node;
DROP POLICY IF EXISTS node_update_policy ON node;
DROP POLICY IF EXISTS node_delete_policy ON node;

CREATE POLICY node_select_policy ON node FOR SELECT
    USING (owner_role = current_user OR owner_role IS NULL);
CREATE POLICY node_insert_policy ON node FOR INSERT
    WITH CHECK (owner_role = current_user OR owner_role IS NULL);
CREATE POLICY node_update_policy ON node FOR UPDATE
    USING (owner_role = current_user)
    WITH CHECK (owner_role = current_user);
CREATE POLICY node_delete_policy ON node FOR DELETE
    USING (owner_role = current_user);

DROP POLICY IF EXISTS edge_select_policy ON edge;
DROP POLICY IF EXISTS edge_insert_policy ON edge;
DROP POLICY IF EXISTS edge_update_policy ON edge;
DROP POLICY IF EXISTS edge_delete_policy ON edge;

CREATE POLICY edge_select_policy ON edge FOR SELECT
    USING (owner_role = current_user OR owner_role IS NULL);
CREATE POLICY edge_insert_policy ON edge FOR INSERT
    WITH CHECK (owner_role = current_user OR owner_role IS NULL);
CREATE POLICY edge_update_policy ON edge FOR UPDATE
    USING (owner_role = current_user)
    WITH CHECK (owner_role = current_user);
CREATE POLICY edge_delete_policy ON edge FOR DELETE
    USING (owner_role = current_user);

-- Episodes are append-only: no UPDATE policy is defined intentionally.
DROP POLICY IF EXISTS episode_select_policy ON episode;
DROP POLICY IF EXISTS episode_insert_policy ON episode;
DROP POLICY IF EXISTS episode_delete_policy ON episode;

CREATE POLICY episode_select_policy ON episode FOR SELECT
    USING (owner_role = current_user);
CREATE POLICY episode_insert_policy ON episode FOR INSERT
    WITH CHECK (owner_role = current_user);
CREATE POLICY episode_delete_policy ON episode FOR DELETE
    USING (owner_role = current_user);
