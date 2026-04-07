-- Add hierarchy columns to ontology_domains
ALTER TABLE ontology_domains
    ADD COLUMN IF NOT EXISTS parent_id INTEGER REFERENCES ontology_domains(id),
    ADD COLUMN IF NOT EXISTS depth INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS path TEXT NOT NULL DEFAULT '';

-- Backfill existing rows: root domains get depth=0 and path=slug
UPDATE ontology_domains SET path = slug WHERE path = '';

-- Indexes for hierarchy lookups
CREATE INDEX IF NOT EXISTS idx_ontology_domains_parent_id ON ontology_domains (parent_id);
CREATE INDEX IF NOT EXISTS idx_ontology_domains_path ON ontology_domains (path);
