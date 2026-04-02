-- =============================================================
-- Default ontology seed data
-- =============================================================

-- Default node types
INSERT INTO node_type (name, description) VALUES
    ('Concept',    'Abstract idea or topic'),
    ('Person',     'Human individual'),
    ('Document',   'Source document or file'),
    ('Event',      'Something that happened at a specific time'),
    ('Tool',       'Software tool, library, or technology'),
    ('Preference', 'User preference or opinion')
ON CONFLICT (name) DO NOTHING;

-- Default edge types
INSERT INTO edge_type (name, description) VALUES
    ('RELATES_TO',   'General relationship'),
    ('MENTIONS',     'Source mentions target'),
    ('CAUSED_BY',    'Target caused source'),
    ('FOLLOWS',      'Source follows target in sequence'),
    ('AUTHORED',     'Source authored target'),
    ('USES',         'Source uses target'),
    ('CONTRADICTS',  'Source contradicts target'),
    ('SUPPORTS',     'Source supports/confirms target'),
    ('SUMMARIZES',   'Source is a summary of target'),
    ('DERIVED_FROM', 'Source was derived from target')
ON CONFLICT (name) DO NOTHING;
