CREATE TABLE IF NOT EXISTS ontology_domains (
    id SERIAL PRIMARY KEY,
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    schema_name TEXT,
    seed BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    created_by TEXT
);

CREATE INDEX IF NOT EXISTS idx_ontology_domains_slug ON ontology_domains (slug);

INSERT INTO ontology_domains (slug, name, description, schema_name, seed) VALUES
('user_profile', 'User Profile & Preferences',
 'Personal preferences, goals, habits, values, opinions, communication style, routines, and work style preferences. Knowledge about what the user likes, dislikes, wants to achieve, and how they prefer to work.',
 'ncx_shared__user_profile', true),
('technical_knowledge', 'Technical Knowledge',
 'Programming languages, frameworks, libraries, tools, architecture patterns, APIs, technical concepts, best practices, and engineering approaches. Knowledge about technologies, how they work, and how to use them.',
 'ncx_shared__technical_knowledge', true),
('work_context', 'Work & Projects',
 'Ongoing projects, tasks, deadlines, team members, organizations, meetings, decisions, and professional activities. Knowledge about what is being worked on, by whom, and when.',
 'ncx_shared__work_context', true),
('domain_knowledge', 'Domain Knowledge',
 'General factual knowledge, industry concepts, scientific facts, business concepts, market trends, and domain-specific expertise. Broad knowledge that does not fit the other specific categories.',
 'ncx_shared__domain_knowledge', true)
ON CONFLICT (slug) DO NOTHING;
