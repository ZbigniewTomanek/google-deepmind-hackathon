-- Default node types
INSERT INTO {schema}.node_type (name, description) VALUES
    ('Concept',    'Abstract idea or topic'),
    ('Person',     'Human individual'),
    ('Document',   'Source document or file'),
    ('Event',      'Something that happened at a specific time'),
    ('Tool',       'Software tool, library, or technology'),
    ('Preference', 'User preference or opinion')
ON CONFLICT (name) DO NOTHING;

-- Default edge types
INSERT INTO {schema}.edge_type (name, description) VALUES
    ('RELATES_TO',   'General relationship'),
    ('MENTIONS',     'Source mentions target'),
    ('CAUSED_BY',    'Target caused source'),
    ('FOLLOWS',      'Source follows target in sequence'),
    ('AUTHORED',     'Source authored target'),
    ('USES',         'Source uses target'),
    ('CONTRADICTS',  'Source contradicts target'),
    ('SUPPORTS',     'Source supports/confirms target'),
    ('SUMMARIZES',   'Source is a summary of target'),
    ('DERIVED_FROM', 'Source was derived from target'),
    ('SUPERSEDES',   'Source supersedes/replaces target — target is outdated'),
    ('CORRECTS',     'Source corrects an error or misconception in target')
ON CONFLICT (name) DO NOTHING;
