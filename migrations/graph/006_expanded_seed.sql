-- Expanded seed ontology (Plan 28, Stage 2)
-- Adds 14 node types + 11 edge types alongside existing 003_seed_ontology.sql types.
-- ON CONFLICT DO NOTHING makes this safe for existing and new schemas.

INSERT INTO {schema}.node_type (name, description) VALUES
    ('Organization', 'Company, institution, or group'),
    ('Location',     'Physical place or address'),
    ('Project',      'Planned endeavor with goals and tasks'),
    ('Activity',     'Physical or mental activity'),
    ('Asset',        'Physical object or piece of equipment'),
    ('Substance',    'Supplement, medication, or consumed substance'),
    ('Metric',       'Quantitative measurement or score'),
    ('Symptom',      'Health symptom or medical condition'),
    ('Goal',         'Objective or target to achieve'),
    ('Task',         'Specific action to complete'),
    ('Emotion',      'Emotional or psychological state'),
    ('Recipe',       'Instructions for preparing food'),
    ('Protocol',     'Structured intervention or procedure'),
    ('Routine',      'Recurring behavioral pattern or habit')
ON CONFLICT (name) DO NOTHING;

INSERT INTO {schema}.edge_type (name, description) VALUES
    ('HAS_GOAL',   'Entity has a goal or objective'),
    ('WORKS_ON',   'Person works on project'),
    ('WORKS_FOR',  'Person works for organization'),
    ('LOCATED_AT', 'Entity is at a location'),
    ('PART_OF',    'Entity is part of another entity'),
    ('EXPERIENCED','Person experienced event or state'),
    ('CONSUMES',   'Person consumes substance or food'),
    ('PERFORMS',   'Person performs activity or routine'),
    ('OWNS',       'Person or org owns an asset'),
    ('RECOMMENDS', 'Source recommends target'),
    ('IMPROVES',   'Source improves or alleviates target')
ON CONFLICT (name) DO NOTHING;
