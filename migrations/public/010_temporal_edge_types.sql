-- Temporal edge types for fact supersession (Plan 18, Stage 6)
INSERT INTO edge_type (name, description) VALUES
  ('SUPERSEDES', 'Source supersedes/replaces target — target is outdated'),
  ('CORRECTS', 'Source corrects an error or misconception in target')
ON CONFLICT (name) DO NOTHING;
